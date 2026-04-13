"""Rich Live dashboard that tails agent log files."""

import json
import threading
import time
from collections import deque
from pathlib import Path

from rich.align import Align
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from agents.streaming import _SENTENCE_BOUNDARY_RE, format_log_line

_AGENT_COLORS = {
    "planner": "blue",
    "executor": "green",
    "monitor": "yellow",
}

_MIN_WIDTH = 80
_MIN_HEIGHT = 24
_STATS_CACHE_TTL = 10.0  # seconds
_PLANS_DIR = Path(".plans")


class EventBuffer:
    """Thread-safe ring buffer for agent log lines."""

    def __init__(self, max_lines: int = 100):
        self._buffer: deque[str] = deque(maxlen=max_lines)
        self._lock = threading.Lock()

    def append(self, line: str) -> None:
        with self._lock:
            self._buffer.append(line)

    def get_lines(self) -> list[str]:
        with self._lock:
            return list(self._buffer)

    def clear(self) -> None:
        with self._lock:
            self._buffer.clear()


_MAX_PARTIAL_CHARS = 4000


def _append_complete_chunks(buffer: EventBuffer, partial: str) -> str:
    """Emit complete line/sentence chunks from partial text and return rest."""
    while "\n" in partial:
        line, partial = partial.split("\n", 1)
        if line.strip():
            buffer.append(line)

    while True:
        match = _SENTENCE_BOUNDARY_RE.search(partial)
        if not match:
            break
        end = match.end()
        chunk = partial[:end].strip()
        if chunk:
            buffer.append(chunk)
        partial = partial[end:]

    return partial


def tail_file_stream(
    log_file: str, buffer: EventBuffer, stop_event: threading.Event
) -> None:
    """Tail a log file, appending new lines to the buffer.

    Reads from the start (fresh per-run logs). Runs until stop_event
    is set or the file is deleted.

    Buffers partial stream tokens and emits finalized chunks only:
    newline-terminated lines first, then sentence-like chunks as a
    fallback. This keeps panels readable while still near-live.
    """
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            partial = ""
            while not stop_event.is_set():
                chunk = f.read(1024)
                if chunk:
                    partial += chunk
                    partial = _append_complete_chunks(buffer, partial)

                    if len(partial) > _MAX_PARTIAL_CHARS:
                        cutoff = partial.rfind(" ")
                        if cutoff <= 0:
                            cutoff = _MAX_PARTIAL_CHARS
                        forced = partial[:cutoff].strip()
                        if forced:
                            buffer.append(forced)
                        partial = partial[cutoff:].lstrip()
                else:
                    time.sleep(0.1)

            if partial.strip():
                buffer.append(partial.strip())
    except (OSError, FileNotFoundError):
        pass


# Module-level cache for stats
_stats_cache: dict = {}
_stats_cache_time: float = 0.0


def _get_article_stats() -> dict:
    """Fetch article statistics from database.

    Returns cached data if within TTL, otherwise queries database.
    """
    global _stats_cache, _stats_cache_time

    now = time.monotonic()
    if _stats_cache and (now - _stats_cache_time) < _STATS_CACHE_TTL:
        return _stats_cache

    try:
        from config import Database
        from database.connection import get_connection

        with get_connection(Database.path) as conn:
            # Article counts and pipeline health
            cursor = conn.execute("""SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN parsed_at IS NOT NULL THEN 1 ELSE 0 END)
                        AS parsed,
                    SUM(CASE WHEN parsed_at IS NULL THEN 1 ELSE 0 END)
                        AS unparsed,
                    SUM(CASE WHEN content IS NOT NULL AND content != ''
                        THEN 1 ELSE 0 END) AS with_content,
                    SUM(CASE WHEN content IS NULL OR content = ''
                        THEN 1 ELSE 0 END) AS without_content,
                    SUM(CASE WHEN content IS NULL AND download_failed = 0
                        THEN 1 ELSE 0 END) AS download_backlog,
                    SUM(CASE WHEN content IS NOT NULL AND parsed_at IS NULL
                        AND parse_failed = 0 THEN 1 ELSE 0 END)
                        AS parse_backlog,
                    SUM(CASE WHEN download_failed = 1 THEN 1 ELSE 0 END)
                        AS download_failed,
                    SUM(CASE WHEN parse_failed = 1 THEN 1 ELSE 0 END)
                        AS parse_failed
                FROM articles""")
            article = cursor.fetchone()
            total = article["total"] or 0
            parsed = article["parsed"] or 0
            unparsed = article["unparsed"] or 0
            with_content = article["with_content"] or 0
            without_content = article["without_content"] or 0
            download_backlog = article["download_backlog"] or 0
            parse_backlog = article["parse_backlog"] or 0
            download_failed = article["download_failed"] or 0
            parse_failed = article["parse_failed"] or 0

            # Freshness windows
            cursor = conn.execute(
                "SELECT COUNT(*) FROM articles "
                "WHERE created_at >= datetime('now', '-1 hour')"
            )
            new_1h = cursor.fetchone()[0]
            cursor = conn.execute(
                "SELECT COUNT(*) FROM articles "
                "WHERE created_at >= datetime('now', '-6 hour')"
            )
            new_6h = cursor.fetchone()[0]
            cursor = conn.execute(
                "SELECT COUNT(*) FROM articles "
                "WHERE created_at >= datetime('now', '-24 hour')"
            )
            new_24h = cursor.fetchone()[0]

            # Oldest unparsed article with content
            cursor = conn.execute("""SELECT MIN(created_at) FROM articles
                    WHERE content IS NOT NULL AND content != ''
                      AND parsed_at IS NULL
                      AND parse_failed = 0""")
            row = cursor.fetchone()
            oldest_unparsed = row[0] if row and row[0] else None

            oldest_unparsed_age = "none"
            if oldest_unparsed:
                cursor = conn.execute(
                    "SELECT CAST((julianday('now') - julianday(?)) * 24 * 60 "
                    "AS INTEGER)",
                    (oldest_unparsed,),
                )
                minutes = cursor.fetchone()[0]
                if minutes is not None:
                    h = int(minutes) // 60
                    m = int(minutes) % 60
                    oldest_unparsed_age = f"{h:02d}h{m:02d}m"

            # Feed count
            cursor = conn.execute("SELECT COUNT(*) FROM feeds")
            feeds = cursor.fetchone()[0]

            # Pending processing (claimed but not completed)
            cursor = conn.execute(
                "SELECT COUNT(*) FROM articles WHERE processing_status = " "'claimed'"
            )
            pending = cursor.fetchone()[0]

            # Last fetch timestamp
            cursor = conn.execute(
                "SELECT MAX(completed_at) FROM fetches WHERE status = " "'completed'"
            )
            row = cursor.fetchone()
            last_fetch = row[0] if row and row[0] else "Never"

            # Articles today
            cursor = conn.execute(
                "SELECT COUNT(*) FROM articles WHERE created_at >= " "date('now')"
            )
            today = cursor.fetchone()[0]

            _stats_cache = {
                "total": total,
                "parsed": parsed,
                "unparsed": unparsed,
                "with_content": with_content,
                "without_content": without_content,
                "download_backlog": download_backlog,
                "parse_backlog": parse_backlog,
                "download_failed": download_failed,
                "parse_failed": parse_failed,
                "feeds": feeds,
                "pending": pending,
                "last_fetch": last_fetch,
                "today": today,
                "new_1h": new_1h,
                "new_6h": new_6h,
                "new_24h": new_24h,
                "oldest_unparsed_age": oldest_unparsed_age,
                "plans_total": 0,
                "plans_pending": 0,
                "plans_executing": 0,
                "plans_completed": 0,
                "plans_failed": 0,
                "plans_campaigns": 0,
                "plans_claimable": 0,
            }

            if _PLANS_DIR.exists():
                plan_counts = {
                    "pending": 0,
                    "executing": 0,
                    "completed": 0,
                    "failed": 0,
                }
                all_plans: list[dict] = []
                for plan_file in _PLANS_DIR.glob("*.json"):
                    try:
                        plan = json.loads(plan_file.read_text(encoding="utf-8"))
                    except (json.JSONDecodeError, OSError):
                        continue
                    all_plans.append(plan)
                    status = str(plan.get("status", "")).lower()
                    if status in plan_counts:
                        plan_counts[status] += 1

                # Count campaigns and claimable plans
                campaigns = 0
                claimable = 0
                completed_ids = {
                    p["id"] for p in all_plans if p.get("status") == "completed"
                }
                for plan in all_plans:
                    if plan.get("plan_kind") == "campaign":
                        campaigns += 1
                    if plan.get("status") != "pending":
                        continue
                    if plan.get("plan_kind") == "campaign":
                        continue
                    parent_id = plan.get("parent_id")
                    if parent_id and parent_id not in completed_ids:
                        continue
                    claimable += 1

                _stats_cache.update(
                    {
                        "plans_total": sum(plan_counts.values()),
                        "plans_pending": plan_counts["pending"],
                        "plans_executing": plan_counts["executing"],
                        "plans_completed": plan_counts["completed"],
                        "plans_failed": plan_counts["failed"],
                        "plans_campaigns": campaigns,
                        "plans_claimable": claimable,
                    }
                )

            _stats_cache_time = now
            return _stats_cache
    except Exception:
        return {
            "total": 0,
            "parsed": 0,
            "unparsed": 0,
            "with_content": 0,
            "without_content": 0,
            "download_backlog": 0,
            "parse_backlog": 0,
            "download_failed": 0,
            "parse_failed": 0,
            "feeds": 0,
            "pending": 0,
            "last_fetch": "Error",
            "today": 0,
            "new_1h": 0,
            "new_6h": 0,
            "new_24h": 0,
            "oldest_unparsed_age": "none",
            "plans_total": 0,
            "plans_pending": 0,
            "plans_executing": 0,
            "plans_completed": 0,
            "plans_failed": 0,
            "plans_campaigns": 0,
            "plans_claimable": 0,
        }


class Dashboard:
    """Rich Live dashboard that tails agent log files.

    Fixed 4-panel layout:
    - Top row: planner (50%) | executor (50%)
    - Bottom row: stats (33%) | monitor (67%)

    Responsive: stacks vertically on narrow terminals (< 100 cols).
    """

    def __init__(self, tick_seconds: int):
        from rich.console import Console

        self.console = Console()
        self.buffers: dict[str, EventBuffer] = {}
        self.agent_status: dict[str, str] = {}
        self.tick_seconds = tick_seconds
        self.agents = ["planner", "executor", "monitor"]
        self.stats_data = _get_article_stats()

    def _buffer_keys_for_agent(self, name: str) -> list[str]:
        """Return all buffer keys for an agent (supports per-instance keys)."""
        keys: list[str] = []
        for key in self.buffers.keys():
            if key == name or key.startswith(name + ":"):
                keys.append(key)
        return sorted(keys)

    def _summarize_lines(self, lines: list[str]) -> dict:
        """Summarize log lines into compact operational counters."""
        summary = {
            "events": len(lines),
            "timeouts": 0,
            "failed": 0,
            "completed": 0,
            "executing": 0,
            "api": 0,
            "last": "Waiting...",
        }
        for line in lines:
            lower = line.lower()
            if "timeout" in lower:
                summary["timeouts"] += 1
            if "failed" in lower or "unsuccessfully" in lower:
                summary["failed"] += 1
            if "completed execution" in lower:
                summary["completed"] += 1
            if "executing tool" in lower:
                summary["executing"] += 1
            if "[httpx]" in lower or "api call" in lower:
                summary["api"] += 1
        if lines:
            summary["last"] = format_log_line(lines[-1])
        return summary

    def _summarize_agent(self, name: str) -> dict:
        """Summarize all buffers belonging to an agent."""
        keys = self._buffer_keys_for_agent(name)
        all_lines: list[str] = []
        for key in keys:
            buffer = self.buffers.get(key)
            if not buffer:
                continue
            all_lines.extend(buffer.get_lines())
        # Keep recent window for summary density
        all_lines = all_lines[-200:]
        summary = self._summarize_lines(all_lines)
        summary["instances"] = len(keys)
        return summary

    def _build_ops_panel(self, name: str) -> Panel:
        """Build compact operations panel for an agent."""
        from rich.console import Group

        color = _AGENT_COLORS.get(name, "white")
        s = self._summarize_agent(name)
        lines = [
            Text(
                f"status:      {self.agent_status.get(name, 'idle')}",
                style="white",
            ),
            Text(f"instances:   {s['instances']}", style="white"),
            Text(f"events:      {s['events']}", style="white"),
            Text(f"executing:   {s['executing']}", style="cyan"),
            Text(f"completed:   {s['completed']}", style="green"),
            Text(f"failed:      {s['failed']}", style="red"),
            Text(f"timeouts:    {s['timeouts']}", style="yellow"),
            Text(f"api calls:   {s['api']}", style="blue"),
            Text(),
            Text("last event", style="bold white"),
            Text(f"{s['last']}", style="dim"),
        ]

        content = Group(*lines)

        status = self.agent_status.get(name, "idle")
        title_extra = f" [{status}]" if status != "idle" else ""

        return Panel(
            content,
            title=f"[bold {color}]{name}{title_extra}[/]",
            border_style=color,
            expand=True,
        )

    def _build_executor_ops_panel(self, height: int) -> Panel:
        """Build executor ops panel with per-instance rows and totals."""
        from rich.console import Group

        keys = self._buffer_keys_for_agent("executor")
        agg = self._summarize_agent("executor")

        lines: list[Text] = []
        lines.append(Text("instances", style="bold white"))
        if not keys:
            lines.append(Text("  none", style="dim"))
        else:
            for key in keys:
                buffer = self.buffers.get(key)
                s = self._summarize_lines(buffer.get_lines()[-80:] if buffer else [])
                instance_id = key.split(":", 1)[1] if ":" in key else "main"
                lines.append(
                    Text(
                        f"  {instance_id:>7}  ev:{s['events']:>3}  "
                        f"ok:{s['completed']:>3}  fail:{s['failed']:>3}  "
                        f"to:{s['timeouts']:>2}",
                        style="white",
                    )
                )

        lines.append(Text())
        lines.append(Text("recent outcomes", style="bold white"))
        lines.append(Text(f"  claim/exec events: {agg['executing']}", style="cyan"))
        lines.append(Text(f"  completed:         {agg['completed']}", style="green"))
        lines.append(Text(f"  failed:            {agg['failed']}", style="red"))
        lines.append(Text(f"  timeouts:          {agg['timeouts']}", style="yellow"))
        lines.append(Text())
        lines.append(Text("last event", style="bold white"))
        lines.append(Text(f"  {agg['last']}", style="dim"))

        # Trim to panel height while preserving top context
        n_visible = max(6, height - 2)
        if len(lines) > n_visible:
            lines = lines[-n_visible:]

        return Panel(
            Group(*lines),
            title="[bold green]executor ops[/]",
            border_style="green",
            expand=True,
        )

    def _build_alerts_panel(self, height: int) -> Panel:
        """Build alert-only panel aggregated from all agent buffers."""
        from rich.console import Group

        alerts: list[Text] = []
        for name, buffer in self.buffers.items():
            for line in buffer.get_lines()[-30:]:
                formatted = format_log_line(line)
                lower = formatted.lower()
                if "timeout" in lower:
                    alerts.append(Text(f"[{name}] {formatted}", style="yellow"))
                elif "✖" in formatted or "failed" in lower:
                    alerts.append(Text(f"[{name}] {formatted}", style="red"))

        if not alerts:
            alerts = [Text("No active alerts", style="dim")]

        n_visible = max(3, height - 2)
        visible = alerts[-n_visible:]
        return Panel(
            Group(*visible),
            title="[bold red]alerts[/]",
            border_style="red",
            expand=True,
        )

    def _build_stats_panel(self, height: int) -> Panel:
        """Build the stats panel with pipeline and plans snapshot."""
        from rich.console import Group

        stats = _get_article_stats()
        lines: list[Text] = []

        # Article stats section
        lines.append(Text("Pipeline snapshot", style="bold white"))
        lines.append(Text(f"  Total:            {stats['total']}", style="white"))
        lines.append(Text(f"  Parsed:           {stats['parsed']}", style="green"))
        lines.append(Text(f"  Unparsed:         {stats['unparsed']}", style="yellow"))
        lines.append(
            Text(f"  Parse backlog:    {stats['parse_backlog']}", style="cyan")
        )
        lines.append(
            Text(
                f"  Download backlog: {stats['download_backlog']}",
                style="cyan",
            )
        )
        lines.append(Text(f"  Parse failed:     {stats['parse_failed']}", style="red"))
        lines.append(
            Text(f"  Download failed:  {stats['download_failed']}", style="red")
        )

        # Plans section
        lines.append(Text())  # blank line
        lines.append(Text("Plans", style="bold white"))
        lines.append(Text(f"  Total:     {stats['plans_total']}", style="white"))
        lines.append(Text(f"  Running:   {stats['plans_executing']}", style="green"))
        lines.append(Text(f"  Pending:   {stats['plans_pending']}", style="yellow"))
        claimable = stats.get("plans_claimable", 0)
        claimable_style = "green bold" if claimable > 0 else "dim"
        lines.append(Text(f"  Claimable: {claimable}", style=claimable_style))
        campaigns = stats.get("plans_campaigns", 0)
        lines.append(
            Text(
                f"  Campaigns: {campaigns}",
                style="magenta" if campaigns > 0 else "dim",
            )
        )
        lines.append(Text(f"  Completed: {stats['plans_completed']}", style="cyan"))
        lines.append(Text(f"  Failed:    {stats['plans_failed']}", style="red"))

        # Feed + fetch section
        lines.append(Text())  # blank line
        lines.append(Text("Feed/Fetch", style="bold white"))
        lines.append(Text(f"  Active feeds:     {stats['feeds']}", style="white"))
        fetch_time = stats["last_fetch"]
        if fetch_time and fetch_time != "Never" and fetch_time != "Error":
            # Truncate to just date/time part
            if "T" in fetch_time:
                fetch_display = fetch_time[:19].replace("T", " ")
            else:
                fetch_display = fetch_time[:19]
        else:
            fetch_display = fetch_time
        lines.append(Text(f"  Last fetch:       {fetch_display}", style="dim"))

        # Pad to fill height
        lines_used = len(lines)
        for _ in range(max(0, height - lines_used)):
            lines.append(Text())

        content = Group(*lines)

        return Panel(
            content,
            title="[bold white]stats[/]",
            border_style="white",
            expand=True,
        )

    def render(self) -> Align:
        # Read current terminal size (supports live resize)
        term_width, term_height = self.console.size

        # Apply minimum size protection
        usable_width = max(_MIN_WIDTH, int(term_width * 0.9))
        usable_height = max(_MIN_HEIGHT, int(term_height * 0.9))

        # Determine layout based on terminal width
        use_vertical_stack = term_width < 100

        header_rows = 3
        panel_area = usable_height - header_rows

        if use_vertical_stack:
            # Vertical stack: header + stats + ops + ops + alerts
            panel_height = panel_area // 4
            lines_per_panel = max(3, panel_height - 2)

            layout = Layout(size=usable_height)
            layout.split_column(
                Layout(name="header", size=header_rows),
                Layout(name="stats"),
                Layout(name="planner"),
                Layout(name="executor"),
                Layout(name="alerts"),
            )

            layout["stats"].update(self._build_stats_panel(lines_per_panel))
            layout["planner"].update(self._build_ops_panel("planner"))
            layout["executor"].update(self._build_executor_ops_panel(lines_per_panel))
            layout["alerts"].update(self._build_alerts_panel(lines_per_panel))
        else:
            # Summary-first 2x2 layout
            panel_height = panel_area // 2  # Each row gets half
            lines_per_panel = max(3, panel_height - 2)

            layout = Layout(size=usable_height)
            layout.split_column(
                Layout(name="header", size=header_rows),
                Layout(name="top_row"),
                Layout(name="bottom_row"),
            )

            # Top row: stats | executor
            layout["top_row"].split_row(
                Layout(name="stats", ratio=1),
                Layout(name="executor", ratio=1),
            )

            # Bottom row: planner ops (33%) | alerts (67%)
            layout["bottom_row"].split_row(
                Layout(name="planner", ratio=1),
                Layout(name="alerts", ratio=2),
            )

            # Build panels
            layout["stats"].update(self._build_stats_panel(lines_per_panel))
            layout["planner"].update(self._build_ops_panel("planner"))
            layout["executor"].update(self._build_executor_ops_panel(lines_per_panel))
            layout["alerts"].update(self._build_alerts_panel(lines_per_panel))

        # Header
        header = Table(show_header=False, border_style="dim", padding=(0, 1))
        header.add_column("title", style="bold white")
        header.add_column("tick", style="cyan", justify="right")
        layout_str = "stacked" if use_vertical_stack else "grid"
        header.add_row(
            f" news48 dashboard [{layout_str}]",
            f"Tick: {self.tick_seconds}s",
        )
        layout["header"].update(header)

        return Align.center(layout, width=usable_width)
