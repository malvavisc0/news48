"""Rich Live dashboard that tails agent log files."""

import json
import re
import threading
import time
from collections import deque
from pathlib import Path

from rich.align import Align
from rich.layout import Layout
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from agents.streaming import format_log_line

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


_SENTENCE_BOUNDARY_RE = re.compile(r"(?:[.!?][\"')\]]*\s+|\n{2,})")
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
            # Article counts
            cursor = conn.execute("SELECT COUNT(*) FROM articles")
            total = cursor.fetchone()[0]
            cursor = conn.execute(
                "SELECT COUNT(*) FROM articles WHERE content IS NOT NULL "
                "AND content != ''"
            )
            with_content = cursor.fetchone()[0]

            # Feed count
            cursor = conn.execute("SELECT COUNT(*) FROM feeds")
            feeds = cursor.fetchone()[0]

            # Pending processing (claimed but not completed)
            cursor = conn.execute(
                "SELECT COUNT(*) FROM articles WHERE processing_status = "
                "'claimed'"
            )
            pending = cursor.fetchone()[0]

            # Last fetch timestamp
            cursor = conn.execute(
                "SELECT MAX(completed_at) FROM fetches WHERE status = "
                "'completed'"
            )
            row = cursor.fetchone()
            last_fetch = row[0] if row and row[0] else "Never"

            # Articles today
            cursor = conn.execute(
                "SELECT COUNT(*) FROM articles WHERE created_at >= "
                "date('now')"
            )
            today = cursor.fetchone()[0]

            _stats_cache = {
                "total": total,
                "with_content": with_content,
                "without_content": total - with_content,
                "feeds": feeds,
                "pending": pending,
                "last_fetch": last_fetch,
                "today": today,
                "plans_total": 0,
                "plans_pending": 0,
                "plans_executing": 0,
                "plans_completed": 0,
                "plans_failed": 0,
            }

            if _PLANS_DIR.exists():
                plan_counts = {
                    "pending": 0,
                    "executing": 0,
                    "completed": 0,
                    "failed": 0,
                }
                for plan_file in _PLANS_DIR.glob("*.json"):
                    try:
                        plan = json.loads(
                            plan_file.read_text(encoding="utf-8")
                        )
                    except (json.JSONDecodeError, OSError):
                        continue
                    status = str(plan.get("status", "")).lower()
                    if status in plan_counts:
                        plan_counts[status] += 1

                _stats_cache.update(
                    {
                        "plans_total": sum(plan_counts.values()),
                        "plans_pending": plan_counts["pending"],
                        "plans_executing": plan_counts["executing"],
                        "plans_completed": plan_counts["completed"],
                        "plans_failed": plan_counts["failed"],
                    }
                )

            _stats_cache_time = now
            return _stats_cache
    except Exception:
        return {
            "total": 0,
            "with_content": 0,
            "without_content": 0,
            "feeds": 0,
            "pending": 0,
            "last_fetch": "Error",
            "today": 0,
            "plans_total": 0,
            "plans_pending": 0,
            "plans_executing": 0,
            "plans_completed": 0,
            "plans_failed": 0,
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

    def _build_panel(self, name: str, lines_per_panel: int) -> Panel:
        """Build a single agent panel rendering content as Markdown."""
        color = _AGENT_COLORS.get(name, "white")
        buffer = self.buffers.get(name)

        if buffer:
            log_lines = buffer.get_lines()
            if log_lines:
                visible = log_lines[-lines_per_panel:]
                formatted = [format_log_line(line) for line in visible]
                md_source = "\n\n".join(formatted)
                content = Markdown(md_source, style=f"{color} dim")
            else:
                content = Text("No logs yet...", style="dim")
        else:
            content = Text("Waiting...", style="dim")

        status = self.agent_status.get(name, "idle")
        title_extra = f" [{status}]" if status != "idle" else ""

        return Panel(
            content,
            title=f"[bold {color}]{name}{title_extra}[/]",
            border_style=color,
            expand=True,
        )

    def _build_stats_panel(self, height: int) -> Panel:
        """Build the stats panel with article counts."""
        from rich.console import Group

        stats = _get_article_stats()
        lines: list[Text] = []

        # Article stats section
        lines.append(Text("Articles", style="bold white"))
        lines.append(Text(f"  Total:     {stats['total']}", style="white"))
        lines.append(Text(f"  Today:     {stats['today']}", style="cyan"))
        lines.append(
            Text(f"  With text: {stats['with_content']}", style="green")
        )
        lines.append(
            Text(f"  No text:   {stats['without_content']}", style="yellow")
        )
        lines.append(Text(f"  Pending:   {stats['pending']}", style="magenta"))

        # Feed stats section
        lines.append(Text())  # blank line
        lines.append(Text("Feeds", style="bold white"))
        lines.append(Text(f"  Active:    {stats['feeds']}", style="white"))

        # Plans section
        lines.append(Text())  # blank line
        lines.append(Text("Plans", style="bold white"))
        lines.append(
            Text(f"  Total:     {stats['plans_total']}", style="white")
        )
        lines.append(
            Text(f"  Running:   {stats['plans_executing']}", style="green")
        )
        lines.append(
            Text(f"  Pending:   {stats['plans_pending']}", style="yellow")
        )
        lines.append(
            Text(f"  Completed: {stats['plans_completed']}", style="cyan")
        )
        lines.append(
            Text(f"  Failed:    {stats['plans_failed']}", style="red")
        )

        # Last fetch section
        lines.append(Text())  # blank line
        lines.append(Text("Last Fetch", style="bold white"))
        fetch_time = stats["last_fetch"]
        if fetch_time and fetch_time != "Never" and fetch_time != "Error":
            # Truncate to just date/time part
            if "T" in fetch_time:
                fetch_display = fetch_time[:19].replace("T", " ")
            else:
                fetch_display = fetch_time[:19]
        else:
            fetch_display = fetch_time
        lines.append(Text(f"  {fetch_display}", style="dim"))

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
            # Vertical stack: header + 4 panels stacked
            panel_height = panel_area // 4
            lines_per_panel = max(3, panel_height - 2)

            layout = Layout(size=usable_height)
            layout.split_column(
                Layout(name="header", size=header_rows),
                Layout(name="planner"),
                Layout(name="executor"),
                Layout(name="stats"),
                Layout(name="monitor"),
            )

            layout["planner"].update(
                self._build_panel("planner", lines_per_panel)
            )
            layout["executor"].update(
                self._build_panel("executor", lines_per_panel)
            )
            layout["stats"].update(self._build_stats_panel(lines_per_panel))
            layout["monitor"].update(
                self._build_panel("monitor", lines_per_panel)
            )
        else:
            # Standard 2x2 grid layout
            panel_height = panel_area // 2  # Each row gets half
            lines_per_panel = max(3, panel_height - 2)

            layout = Layout(size=usable_height)
            layout.split_column(
                Layout(name="header", size=header_rows),
                Layout(name="top_row"),
                Layout(name="bottom_row"),
            )

            # Top row: planner | executor (50% each)
            layout["top_row"].split_row(
                Layout(name="planner"),
                Layout(name="executor"),
            )

            # Bottom row: stats (33%) | monitor (67%)
            layout["bottom_row"].split_row(
                Layout(name="stats", ratio=1),
                Layout(name="monitor", ratio=2),
            )

            # Build panels
            layout["planner"].update(
                self._build_panel("planner", lines_per_panel)
            )
            layout["executor"].update(
                self._build_panel("executor", lines_per_panel)
            )
            layout["monitor"].update(
                self._build_panel("monitor", lines_per_panel)
            )
            layout["stats"].update(self._build_stats_panel(lines_per_panel))

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
