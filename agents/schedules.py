"""Agent schedule configuration, dataclasses, and helpers.

Provides shared definitions used by the Orchestrator and agent
command modules.
"""

import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Optional


@dataclass
class AgentSchedule:
    """Schedule configuration for a single agent."""

    agent_name: str
    task_prompt: str
    interval_minutes: int
    enabled: bool = True
    max_concurrent: int = 1
    max_runtime_minutes: int = 30
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
    process: Optional[subprocess.Popen] = field(default=None, repr=False, compare=False)


# Default schedules
DEFAULT_SCHEDULES: Dict[str, AgentSchedule] = {
    "sentinel": AgentSchedule(
        agent_name="sentinel",
        task_prompt=(
            "Run one sentinel cycle. Gather system health metrics, "
            "evaluate thresholds, create fix plans for detected issues, "
            "and delete feeds that are consistently problematic."
        ),
        interval_minutes=5,
    ),
    "executor": AgentSchedule(
        agent_name="executor",
        task_prompt=(
            "Run one execution cycle. Claim one eligible plan, execute its "
            "steps, verify the success conditions, and set the final plan "
            "status. Do not create plans."
        ),
        interval_minutes=1,
        max_concurrent=5,
    ),
    "parser": AgentSchedule(
        agent_name="parser",
        task_prompt=(
            "Run one parser cycle. Claim eligible downloaded articles from "
            "the database, parse one claimed article at a time, update the "
            "article, and release the claim when finished."
        ),
        interval_minutes=1,
        max_concurrent=5,
    ),
    "fact_checker": AgentSchedule(
        agent_name="fact_checker",
        task_prompt=(
            "Run one fact-check cycle. Claim eligible fact-unchecked "
            "articles, search for evidence, and record verdicts."
        ),
        interval_minutes=5,
        max_concurrent=3,
    ),
}


def _is_process_alive(pid: int) -> bool:
    """Check if a process with the given PID is still running.

    On Linux, treats zombie processes as not alive for orchestration
    purposes so stale PIDs do not block scheduling or shutdown logic.
    """
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)  # Signal 0 = check existence
    except (ProcessLookupError, PermissionError):
        return False

    stat_path = f"/proc/{pid}/stat"
    try:
        stat = open(stat_path, "r", encoding="utf-8").read()
    except OSError:
        return True

    try:
        _pid, remainder = stat.split("(", 1)
        _comm, remainder = remainder.rsplit(")", 1)
        parts = remainder.strip().split()
        state = parts[0]
    except (IndexError, ValueError):
        return True

    return state != "Z"


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
