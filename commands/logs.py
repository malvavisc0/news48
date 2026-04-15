"""Logs command group - inspect and search agent log files."""

import json
import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

import typer

import config
from agents.streaming import _LOG_LINE_RE, format_log_line

from ._common import emit_error

logs_app = typer.Typer(help="Inspect and search agent log files.")


AGENT_CHOICES = ["executor", "sentinel", "fact_checker", "parser"]


# Extract date/time from log filenames: executor-20260406-025724.log
_FILENAME_TS_RE = re.compile(r"^[a-z]+-(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})\d{2}\.log$")


def _timestamp_from_filename(filename: str) -> str:
    """Extract a YYYY-MM-DD HH:MM timestamp from a log filename.

    Filenames follow the pattern {agent}-{YYYYMMDD}-{HHMMSS}.log.
    Returns empty string if the filename doesn't match.
    """
    m = _FILENAME_TS_RE.match(filename)
    if not m:
        return ""
    year, month, day, hour, minute = m.groups()
    return f"{year}-{month}-{day} {hour}:{minute}"


@dataclass
class LogEntry:
    """A single parsed log entry."""

    timestamp: str  # YYYY-MM-DD HH:MM
    module: str  # logger name from brackets
    message: str  # structured message text
    continuation: list[str] = field(default_factory=list)  # trailing prose lines
    source_file: str = ""  # originating .log filename


def parse_log_lines(lines: list[str], source_file: str = "") -> list[LogEntry]:
    """Parse log file lines into structured entries.

    Handles mixed content: structured log lines become entries,
    free-form prose lines attach to the preceding entry as continuation.
    Standalone prose before any structured line gets a timestamp
    derived from the source filename so entries sort correctly.
    """
    entries: list[LogEntry] = []
    current: LogEntry | None = None
    last_timestamp: str = _timestamp_from_filename(source_file)

    for line in lines:
        stripped = line.rstrip()
        if not stripped:
            if current and current.continuation is not None:
                current.continuation.append("")
            continue

        match = _LOG_LINE_RE.match(stripped)
        if match:
            date_str, time_str, module, message = match.groups()
            last_timestamp = f"{date_str} {time_str}"
            current = LogEntry(
                timestamp=last_timestamp,
                module=module,
                message=message,
                source_file=source_file,
            )
            entries.append(current)
        else:
            # Prose line — attach to current entry or create standalone
            if current:
                current.continuation.append(stripped)
            else:
                current = LogEntry(
                    timestamp=last_timestamp,
                    module="",
                    message=stripped,
                    source_file=source_file,
                )
                entries.append(current)
    return entries


def _parse_date(value: str) -> date | None:
    """Parse a date string into a date object.

    Accepts YYYY-MM-DD format or relative keywords: today, yesterday.
    """
    if not value:
        return None
    if value.lower() == "today":
        return date.today()
    if value.lower() == "yesterday":
        return date.today() - timedelta(days=1)
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def get_log_files(
    agent: str | None = None,
    date_filter: date | None = None,
) -> list[Path]:
    """Find log files matching criteria."""
    if not config.LOGS_DIR.exists():
        return []

    pattern = "*.log"
    if agent:
        pattern = f"{agent}-*.log"

    files = sorted(config.LOGS_DIR.glob(pattern), reverse=True)

    if date_filter:
        date_str = date_filter.strftime("%Y%m%d")
        files = [f for f in files if date_str in f.name]

    return files


def filter_entries(
    entries: list[LogEntry],
    plan_id: str | None = None,
    module: str | None = None,
    include_prose: bool = False,
) -> list[LogEntry]:
    """Filter parsed entries by criteria."""
    result = []
    for entry in entries:
        if module and entry.module != module:
            continue
        if plan_id:
            # Search in message AND continuation lines
            all_text = entry.message + " ".join(entry.continuation)
            if plan_id not in all_text:
                continue
        if not include_prose and not entry.module:
            # Skip standalone prose entries unless opted in
            continue
        result.append(entry)
    return result


def _entry_to_dict(entry: LogEntry) -> dict:
    """Convert a LogEntry to a JSON-serialisable dict."""
    d: dict = {
        "timestamp": entry.timestamp,
        "module": entry.module,
        "message": entry.message,
        "source_file": entry.source_file,
    }
    if entry.continuation:
        d["continuation"] = entry.continuation
    return d


def _print_entry(entry: LogEntry, include_prose: bool = False) -> None:
    """Print a single LogEntry in human-readable format."""
    if entry.module:
        print(f"{entry.timestamp} [{entry.module}] {entry.message}")
    else:
        print(entry.message)
    if include_prose and entry.continuation:
        for line in entry.continuation:
            print(line)


@logs_app.command(name="list")
def logs_list(
    agent: str = typer.Option(
        "all",
        "--agent",
        "-a",
        help="Filter by agent type: executor, sentinel, fact_checker, parser",
    ),
    date_str: str = typer.Option(
        "today",
        "--date",
        "-d",
        help="Filter by date: YYYY-MM-DD or 'today', 'yesterday'",
    ),
    plan_id: str = typer.Option(
        None,
        "--plan-id",
        "-p",
        help="Filter by plan ID (searches structured + prose lines)",
    ),
    module: str = typer.Option(
        None,
        "--module",
        "-m",
        help="Filter by module name, e.g. agents._run, httpx",
    ),
    output_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
    limit: int = typer.Option(
        100, "--limit", "-n", help="Maximum number of entries to display"
    ),
    reverse: bool = typer.Option(
        False,
        "--reverse",
        help="Show oldest entries first (default: newest first)",
    ),
    include_prose: bool = typer.Option(
        False, "--include-prose", help="Include free-form agent output"
    ),
) -> None:
    """List and filter structured log entries."""
    # Parse agent filter
    agent_filter = None if agent == "all" else agent
    if agent_filter and agent_filter not in AGENT_CHOICES:
        choices = ", ".join(AGENT_CHOICES)
        emit_error(
            f"Invalid agent type '{agent_filter}'. Choose from: {choices}",
            as_json=output_json,
        )

    # Parse date filter
    date_filter = _parse_date(date_str)
    if date_str and date_filter is None:
        emit_error(
            f"Invalid date '{date_str}'. " "Use YYYY-MM-DD, 'today', or 'yesterday'.",
            as_json=output_json,
        )

    # Discover files
    files = get_log_files(agent=agent_filter, date_filter=date_filter)
    if not files:
        if output_json:
            json.dump([], sys.stdout, indent=2)
            print()
        else:
            print("No matching log files found.")
        return

    # Parse all matching files
    all_entries: list[LogEntry] = []
    for f in files:
        try:
            content = f.read_text(encoding="utf-8")
        except OSError:
            continue
        entries = parse_log_lines(content.splitlines(), source_file=f.name)
        all_entries.extend(entries)

    # Apply filters
    filtered = filter_entries(
        all_entries,
        plan_id=plan_id,
        module=module,
        include_prose=include_prose,
    )

    # Sort: newest first by default, oldest first with --reverse
    filtered.sort(key=lambda e: e.timestamp, reverse=not reverse)

    # Apply limit
    filtered = filtered[:limit]

    # Output
    if output_json:
        json.dump(
            [_entry_to_dict(e) for e in filtered],
            sys.stdout,
            default=str,
            indent=2,
        )
        print()
    else:
        for entry in filtered:
            _print_entry(entry, include_prose=include_prose)


@logs_app.command(name="files")
def logs_files(
    agent: str = typer.Option(
        "all",
        "--agent",
        "-a",
        help="Filter by agent type: executor, sentinel, fact_checker, parser",
    ),
    date_str: str = typer.Option(
        None,
        "--date",
        "-d",
        help="Filter by date: YYYY-MM-DD or 'today', 'yesterday'",
    ),
    output_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """List log files with metadata."""
    # Parse agent filter
    agent_filter = None if agent == "all" else agent
    if agent_filter and agent_filter not in AGENT_CHOICES:
        choices = ", ".join(AGENT_CHOICES)
        emit_error(
            f"Invalid agent type '{agent_filter}'. Choose from: {choices}",
            as_json=output_json,
        )

    # Parse date filter
    date_filter = _parse_date(date_str) if date_str else None
    if date_str and date_filter is None:
        emit_error(
            f"Invalid date '{date_str}'. " "Use YYYY-MM-DD, 'today', or 'yesterday'.",
            as_json=output_json,
        )

    if not config.LOGS_DIR.exists():
        emit_error(
            f"Log directory {config.LOGS_DIR}/ does not exist.",
            as_json=output_json,
        )

    files = get_log_files(agent=agent_filter, date_filter=date_filter)
    if not files:
        if output_json:
            json.dump([], sys.stdout, indent=2)
            print()
        else:
            print("No matching log files found.")
        return

    file_data = []
    for f in files:
        stat = f.stat()
        file_data.append(
            {
                "name": f.name,
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            }
        )

    if output_json:
        json.dump(file_data, sys.stdout, default=str, indent=2)
        print()
    else:
        for fd in file_data:
            size_kb = fd["size"] / 1024
            print(f"{fd['name']}  {size_kb:.1f}KB  {fd['modified']}")


@logs_app.command(name="show")
def logs_show(
    filename: str = typer.Argument(..., help="Log file name or stem"),
    raw: bool = typer.Option(False, "--raw", help="Print without formatting"),
    output_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """Display an entire log file."""
    # Resolve filename: accept stem or full name
    path = config.LOGS_DIR / filename
    if not path.exists() and not filename.endswith(".log"):
        path = config.LOGS_DIR / f"{filename}.log"

    if not path.exists():
        emit_error(f"Log file not found: {filename}", as_json=output_json)

    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        emit_error(f"Cannot read log file: {exc}", as_json=output_json)

    if raw:
        print(content, end="")
        return

    if output_json:
        entries = parse_log_lines(content.splitlines(), source_file=path.name)
        json.dump(
            [_entry_to_dict(e) for e in entries],
            sys.stdout,
            default=str,
            indent=2,
        )
        print()
        return

    # Formatted: use format_log_line for structured lines,
    # pass through prose as-is.
    for line in content.splitlines():
        print(format_log_line(line))
