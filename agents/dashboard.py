"""Rich Live dashboard that tails agent log files."""

import re
import threading
import time
from collections import deque
from typing import Dict, List, Optional

from rich.align import Align
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from agents.streaming import format_log_line

_AGENT_COLORS = {
    "planner": "blue",
    "executor": "green",
    "monitor": "yellow",
}

_HEADER_ROWS = 3
_FOOTER_ROWS = 3
_PANEL_BORDER_ROWS = 2  # top + bottom border per panel


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


def _normalize_line(line: str) -> str:
    """Normalize noisy stream fragments for panel readability."""
    compact = " ".join(line.replace("\t", " ").split())
    if len(compact) > 500:
        return compact[:497] + "..."
    return compact


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


class Dashboard:
    """Rich Live dashboard that tails agent log files.

    Fills 90% of the terminal width and height. Dynamically adapts
    the number of visible log lines per panel when the terminal is
    resized.
    """

    def __init__(
        self,
        tick_seconds: int,
        agents: Optional[List[str]] = None,
    ):
        from rich.console import Console

        self.console = Console()
        self.buffers: Dict[str, EventBuffer] = {}
        self.agent_status: Dict[str, str] = {}
        self.tick_seconds = tick_seconds
        self.agents = agents or ["planner", "executor"]

    def _build_panel(self, name: str, lines_per_panel: int) -> Panel:
        """Build a single agent panel."""
        color = _AGENT_COLORS.get(name, "white")
        buffer = self.buffers.get(name)
        if buffer:
            lines = buffer.get_lines()
            content = Text()
            for line in lines[-lines_per_panel:]:
                formatted = format_log_line(line)
                normalized = _normalize_line(formatted)
                if not normalized:
                    continue
                content.append(normalized + "\n", style=f"{color} dim")
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

    def render(self) -> Align:
        # Read current terminal size (supports live resize)
        term_width, term_height = self.console.size
        usable_width = int(term_width * 0.9)
        usable_height = int(term_height * 0.9)

        # Calculate how many log lines fit per panel
        num_agents = len(self.agents)
        if num_agents <= 2:
            panel_rows = 2
        else:
            panel_rows = 2  # top row + bottom row

        agent_area = usable_height - _HEADER_ROWS - _FOOTER_ROWS
        lines_per_panel = max(
            3, (agent_area // panel_rows) - _PANEL_BORDER_ROWS
        )

        layout = Layout(size=usable_height)
        layout.split_column(
            Layout(name="header", size=_HEADER_ROWS),
            Layout(name="agents"),
            Layout(name="footer", size=_FOOTER_ROWS),
        )

        # Header
        header = Table(show_header=False, border_style="dim", padding=(0, 1))
        header.add_column("title", style="bold white")
        header.add_column("tick", style="cyan", justify="right")
        header.add_row(" news48 dashboard", f"Tick: {self.tick_seconds}s")
        layout["header"].update(header)

        # Agent panels - dynamic layout based on agent count
        panels = [
            self._build_panel(name, lines_per_panel) for name in self.agents
        ]

        agents_layout = Layout()
        if len(panels) == 1:
            agents_layout.update(panels[0])
        elif len(panels) == 2:
            agents_layout.split_row(Layout(panels[0]), Layout(panels[1]))
        elif len(panels) >= 3:
            agents_layout.split_column(
                Layout(name="top_row"),
                Layout(name="bottom_row"),
            )
            agents_layout["top_row"].update(panels[0])
            agents_layout["bottom_row"].split_row(
                *[Layout(p) for p in panels[1:]]
            )
        layout["agents"].update(agents_layout)

        # Footer - status summary
        parts = []
        running = [n for n, s in self.agent_status.items() if s == "running"]
        completed = [
            n for n, s in self.agent_status.items() if s == "completed"
        ]
        if completed:
            parts.append(f"Completed: {', '.join(completed)}")
        if running:
            parts.append(f"Running: {', '.join(running)}")
        footer_text = "  " + "  |  ".join(parts) if parts else "  Idle"
        layout["footer"].update(Text(footer_text, style="dim"))

        # Center horizontally at 90% width
        return Align.center(layout, width=usable_width)
