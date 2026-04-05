"""Agent schedule configuration, dataclasses, and helpers.

Provides shared definitions used by the Orchestrator and agent
command modules.
"""

import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

_STATE_FILE = Path(".orchestrator.json")
_LOGS_DIR = Path(".logs")


@dataclass
class AgentSchedule:
    """Schedule configuration for a single agent."""

    agent_name: str
    task_prompt: str
    interval_minutes: int
    enabled: bool = True
    last_run: Optional[str] = None
    last_result: Optional[str] = None
    last_error: Optional[str] = None


@dataclass
class RunningAgent:
    """Tracks a forked agent subprocess."""

    pid: int
    agent_name: str
    started_at: str
    log_file: str
    process: Optional[subprocess.Popen] = field(
        default=None, repr=False, compare=False
    )


# Default schedules
DEFAULT_SCHEDULES: Dict[str, AgentSchedule] = {
    "pipeline": AgentSchedule(
        agent_name="pipeline",
        task_prompt=(
            "Run a full pipeline cycle: fetch all feeds to update article "
            "metadata, then for each feed domain check for empty articles "
            "and fork a download process per domain, then for each feed "
            "domain check for downloaded-but-unparsed articles and fork a "
            "parse process per domain, then purge expired articles."
        ),
        interval_minutes=1,
    ),
    "monitor": AgentSchedule(
        agent_name="monitor",
        task_prompt="Perform a full system health check and report any "
        "issues.",
        interval_minutes=10,
    ),
    "reporter": AgentSchedule(
        agent_name="reporter",
        task_prompt="Generate a daily pipeline report.",
        interval_minutes=1440,  # 24 hours
    ),
    "checker": AgentSchedule(
        agent_name="checker",
        task_prompt=(
            "Fact-check up to 5 recently parsed articles, focusing on "
            "politics, health, science, and conflict categories."
        ),
        interval_minutes=360,  # 6 hours
    ),
}


def _is_process_alive(pid: int) -> bool:
    """Check if a process with the given PID is still running."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)  # Signal 0 = check existence
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _duration_since(iso_timestamp: str) -> str:
    """Return a human-readable duration since the given ISO timestamp."""
    try:
        start = datetime.fromisoformat(iso_timestamp)
        elapsed = datetime.now(timezone.utc) - start
        total_seconds = int(elapsed.total_seconds())
        if total_seconds < 60:
            return f"{total_seconds}s"
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        if minutes < 60:
            return f"{minutes}m{seconds}s"
        hours = minutes // 60
        minutes = minutes % 60
        return f"{hours}h{minutes}m"
    except (ValueError, TypeError):
        return "?"


def _tail_file(path: str, lines: int = 20) -> Optional[str]:
    """Read the last N lines of a file."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
            tail = all_lines[-lines:] if len(all_lines) > lines else all_lines
            return "".join(tail).strip()
    except (OSError, FileNotFoundError):
        return None
