"""Orchestrator -- Python dispatcher that runs agents on a schedule.

Supports two modes:
- One-shot: ``agents run`` checks what's due and runs agents inline.
- Daemon: ``agents start`` runs a continuous loop, forking each agent
  as an independent subprocess and tracking its outcome.
"""

import json
import logging
import os
import signal
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Literal, Optional

logger = logging.getLogger(__name__)

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


class Orchestrator:
    """Python dispatcher that invokes agents with predefined task prompts.

    The orchestrator is NOT an LLM agent. It runs agents on a timer
    with predefined task prompts. This is a scheduling problem, not a
    reasoning problem.

    In daemon mode (``start``), each agent is forked as its own
    subprocess via ``uv run news48 agents run --agent <name>``.
    The orchestrator tracks PIDs, polls for completion, reads exit
    codes, and persists schedule state to ``.orchestrator.json``.
    """

    def __init__(
        self,
        schedules: Optional[Dict[str, AgentSchedule]] = None,
    ):
        self.schedules = schedules or {
            name: AgentSchedule(
                agent_name=s.agent_name,
                task_prompt=s.task_prompt,
                interval_minutes=s.interval_minutes,
                enabled=s.enabled,
                last_run=s.last_run,
            )
            for name, s in DEFAULT_SCHEDULES.items()
        }
        self.running: Dict[str, RunningAgent] = {}

    def load_state(self) -> None:
        """Load schedule state from ``.orchestrator.json``.

        Restores ``last_run``, ``last_result``, and ``last_error`` for
        each schedule, and any previously running agent entries (their
        processes will be checked on the next tick).
        """
        if not _STATE_FILE.exists():
            return
        try:
            data = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(f"Could not load state: {exc}")
            return

        # Restore schedule state
        for name, sched_data in data.get("schedules", {}).items():
            if name in self.schedules:
                self.schedules[name].last_run = sched_data.get("last_run")
                self.schedules[name].last_result = sched_data.get(
                    "last_result"
                )
                self.schedules[name].last_error = sched_data.get("last_error")

        # Restore running agent records (processes are gone after restart,
        # but we mark them as failed-unknown so we know they didn't finish)
        for name, run_data in data.get("running", {}).items():
            pid = run_data.get("pid", 0)
            if not _is_process_alive(pid):
                # Process is gone -- mark as completed with unknown result
                if name in self.schedules:
                    self.schedules[name].last_run = run_data.get("started_at")
                    self.schedules[name].last_result = "unknown"
                    self.schedules[name].last_error = (
                        "Process disappeared (orchestrator restarted?)"
                    )
            else:
                # Process is still running from a previous session
                self.running[name] = RunningAgent(
                    pid=pid,
                    agent_name=name,
                    started_at=run_data.get("started_at", ""),
                    log_file=run_data.get("log_file", ""),
                )

    def save_state(self) -> None:
        """Persist schedule state to ``.orchestrator.json``."""
        data: Dict[str, Any] = {
            "schedules": {},
            "running": {},
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        for name, schedule in self.schedules.items():
            data["schedules"][name] = {
                "last_run": schedule.last_run,
                "last_result": schedule.last_result,
                "last_error": schedule.last_error,
            }
        for name, running in self.running.items():
            data["running"][name] = {
                "pid": running.pid,
                "started_at": running.started_at,
                "log_file": running.log_file,
            }
        try:
            _STATE_FILE.write_text(
                json.dumps(data, indent=2, default=str),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.error(f"Could not save state: {exc}")

    def _should_run(self, schedule: AgentSchedule) -> bool:
        """Check if an agent should run based on its schedule."""
        if not schedule.enabled:
            return False
        if schedule.agent_name in self.running:
            return False  # Already running
        if schedule.last_run is None:
            return True
        try:
            last_run = datetime.fromisoformat(schedule.last_run)
            now = datetime.now(timezone.utc)
            interval = timedelta(minutes=schedule.interval_minutes)
            return (now - last_run) >= interval
        except (ValueError, TypeError):
            return True

    async def run_agent(
        self,
        name: Literal["pipeline", "monitor", "reporter", "checker"],
        task: str,
    ) -> Dict[str, Any]:
        """Run a specific agent inline with a task prompt.

        This is the one-shot mode used by ``agents run --agent <name>``.

        Args:
            name: Agent name (pipeline, monitor, reporter, checker).
            task: Task prompt to send to the agent.

        Returns:
            Dict with agent name, result, and error (if any).
        """
        if name not in ["pipeline", "monitor", "reporter", "checker"]:
            return {
                "agent": name,
                "result": None,
                "error": f"Unknown agent: {name}",
            }

        if name in self.running:
            running_info = self.running[name]
            pid = running_info.pid
            started = running_info.started_at
            return {
                "agent": name,
                "result": None,
                "error": (
                    f"Agent '{name}' is already running "
                    f"(PID {pid}, started at {started})"
                ),
            }

        if name == "pipeline":
            from agents.pipeline import run as agent_run
        elif name == "monitor":
            from agents.monitor import run as agent_run
        elif name == "reporter":
            from agents.reporter import run as agent_run
        elif name == "checker":
            from agents.checker import run as agent_run

        try:
            result = await agent_run(task)
            schedule = self.schedules.get(name)
            if schedule:
                schedule.last_run = datetime.now(timezone.utc).isoformat()
                schedule.last_result = "success"
                schedule.last_error = None
            self.save_state()
            return {"agent": name, "result": result, "error": None}
        except Exception as e:
            logger.error(f"Agent {name} failed: {e}")
            schedule = self.schedules.get(name)
            if schedule:
                schedule.last_run = datetime.now(timezone.utc).isoformat()
                schedule.last_result = "error"
                schedule.last_error = str(e)
            self.save_state()
            return {"agent": name, "result": None, "error": str(e)}

    async def run_due_agents(self) -> Dict[str, Any]:
        """Run all agents that are due (inline, one-shot mode).

        Returns:
            Dict with agents_run list, results dict, and timestamp.
        """
        results: Dict[str, Any] = {}
        agents_run: list[str] = []

        for name, schedule in self.schedules.items():
            if not self._should_run(schedule):
                continue
            result = await self.run_agent(name, schedule.task_prompt)
            results[name] = result
            agents_run.append(name)

        return {
            "agents_run": agents_run,
            "results": results,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def fork_agent(self, name: str, task: Optional[str] = None) -> bool:
        """Fork an agent as an independent subprocess.

        Runs ``uv run news48 agents run --agent <name>`` in a new
        process, redirecting stdout/stderr to a log file.

        Args:
            name: Agent name to fork.
            task: Optional custom task prompt.

        Returns:
            True if the agent was forked, False on error.
        """
        if name in self.running:
            logger.warning(
                f"Agent {name} is already running (PID "
                f"{self.running[name].pid})"
            )
            return False

        _LOGS_DIR.mkdir(exist_ok=True)
        now = datetime.now(timezone.utc)
        timestamp = now.strftime("%Y%m%d-%H%M%S")
        log_file = str(_LOGS_DIR / f"{name}-{timestamp}.log")

        cmd = [
            "uv",
            "run",
            "news48",
            "agents",
            "run",
            "--agent",
            name,
            "--json",
        ]
        if task:
            cmd.extend(["--task", task])

        try:
            log_fh = open(log_file, "w", encoding="utf-8")
            proc = subprocess.Popen(
                cmd,
                stdout=log_fh,
                stderr=subprocess.STDOUT,
                cwd=os.getcwd(),
                start_new_session=True,  # Detach from parent
            )
            log_fh.close()  # Child inherited the fd
            self.running[name] = RunningAgent(
                pid=proc.pid,
                agent_name=name,
                started_at=now.isoformat(),
                log_file=log_file,
                process=proc,
            )
            logger.info(
                f"Forked agent {name} as PID {proc.pid} " f"→ {log_file}"
            )
            return True
        except Exception as exc:
            logger.error(f"Failed to fork agent {name}: {exc}")
            return False

    def check_running(self) -> Dict[str, Dict[str, Any]]:
        """Poll running agent subprocesses for completion.

        For each completed process, updates the schedule state with
        the exit code and cleans up the running tracker.

        Returns:
            Dict of agent names that completed, with their results.
        """
        completed: Dict[str, Dict[str, Any]] = {}
        finished_names: list[str] = []

        for name, running in self.running.items():
            proc = running.process
            pid = running.pid

            # If we don't have a process handle (e.g., restored from state
            # after restart), check if the PID is still alive
            if proc is None:
                if not _is_process_alive(pid):
                    finished_names.append(name)
                    completed[name] = {
                        "pid": pid,
                        "exit_code": None,
                        "result": "unknown",
                        "log_file": running.log_file,
                        "duration": _duration_since(running.started_at),
                    }
                continue

            # Poll the process
            exit_code = proc.poll()
            if exit_code is not None:
                finished_names.append(name)
                result = "success" if exit_code == 0 else "error"
                error_msg = None

                # Try to read the last few lines of the log for context
                if exit_code != 0:
                    error_msg = _tail_file(running.log_file, lines=20)

                completed[name] = {
                    "pid": pid,
                    "exit_code": exit_code,
                    "result": result,
                    "error": error_msg,
                    "log_file": running.log_file,
                    "duration": _duration_since(running.started_at),
                }

                # Update schedule state
                schedule = self.schedules.get(name)
                if schedule:
                    schedule.last_run = running.started_at
                    schedule.last_result = result
                    schedule.last_error = error_msg

        # Remove completed agents from running
        for name in finished_names:
            del self.running[name]

        return completed

    def tick(self) -> Dict[str, Any]:
        """Run one orchestrator cycle.

        1. Check running processes for completion.
        2. Fork due agents that aren't running.
        3. Save state.

        Returns:
            Dict summarizing what happened this tick.
        """
        # 1. Check completed agents
        completed = self.check_running()

        # 2. Fork due agents
        forked: list[str] = []
        for name, schedule in self.schedules.items():
            if self._should_run(schedule):
                if self.fork_agent(name):
                    forked.append(name)

        # 3. Save state
        self.save_state()

        return {
            "completed": completed,
            "forked": forked,
            "running": list(self.running.keys()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def start(self, tick_seconds: int = 60) -> None:
        """Run the orchestrator in a continuous loop.

        Each tick:
        1. Loads persisted state.
        2. Checks running processes for completion.
        3. Forks due agents as subprocesses.
        4. Saves state.
        5. Sleeps for ``tick_seconds``.

        Args:
            tick_seconds: Seconds between each tick (default: 60).
        """
        logger.info(f"Orchestrator starting (tick every {tick_seconds}s)")
        self.load_state()

        try:
            while True:
                result = self.tick()

                # Log tick summary
                n_completed = len(result["completed"])
                n_forked = len(result["forked"])
                n_running = len(result["running"])

                if n_completed or n_forked:
                    logger.info(
                        f"Tick: {n_forked} forked, "
                        f"{n_completed} completed, "
                        f"{n_running} running"
                    )
                    # Log details for completed agents
                    for name, info in result["completed"].items():
                        status = info["result"]
                        duration = info.get("duration", "?")
                        logger.info(
                            f"  {name}: {status} "
                            f"(exit={info.get('exit_code')}, "
                            f"duration={duration})"
                        )
                    for name in result["forked"]:
                        logger.info(
                            f"  {name}: forked → "
                            f"PID {self.running[name].pid}"
                        )

                time.sleep(tick_seconds)
        except KeyboardInterrupt:
            logger.info("Orchestrator stopped by user")
            self.save_state()

    def stop_agent(self, name: str) -> Dict[str, Any]:
        """Stop a running agent: SIGTERM, wait 5s, then SIGKILL."""
        if name not in self.running:
            return {"stopped": [], "already_stopped": [name]}

        running = self.running[name]
        pid = running.pid

        # Send SIGTERM to process group
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        except OSError:
            pass

        # Wait up to 5 seconds
        for _ in range(50):
            time.sleep(0.1)
            if not _is_process_alive(pid):
                break
        else:
            try:
                os.killpg(os.getpgid(pid), signal.SIGKILL)
            except OSError:
                pass

        # Update schedule
        schedule = self.schedules.get(name)
        if schedule:
            schedule.last_run = running.started_at
            schedule.last_result = "stopped"
            schedule.last_error = "Stopped by user"

        del self.running[name]
        self.save_state()
        return {"stopped": [name], "already_stopped": []}

    def stop_all(self) -> Dict[str, Any]:
        """Stop all running agents."""
        stopped, already = [], []
        for name in list(self.running.keys()):
            result = self.stop_agent(name)
            stopped.extend(result["stopped"])
            already.extend(result["already_stopped"])
        return {"stopped": stopped, "already_stopped": already}

    def get_status(self) -> Dict[str, Any]:
        """Get status of all agent schedules.

        Returns:
            Dict mapping agent names to their schedule status.
        """
        status = {}
        for name, schedule in self.schedules.items():
            next_run = "immediate"
            if schedule.last_run and schedule.enabled:
                try:
                    last = datetime.fromisoformat(schedule.last_run)
                    interval = timedelta(minutes=schedule.interval_minutes)
                    next_run = (last + interval).isoformat()
                except (ValueError, TypeError):
                    pass
            elif not schedule.enabled:
                next_run = "disabled"

            is_running = name in self.running
            running_info = None
            if is_running:
                r = self.running[name]
                running_info = {
                    "pid": r.pid,
                    "started_at": r.started_at,
                    "log_file": r.log_file,
                }

            status[name] = {
                "enabled": schedule.enabled,
                "interval_minutes": schedule.interval_minutes,
                "last_run": schedule.last_run,
                "last_result": schedule.last_result,
                "last_error": schedule.last_error,
                "next_run": next_run,
                "task_prompt": schedule.task_prompt,
                "running": is_running,
                "running_info": running_info,
            }
        return status


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
