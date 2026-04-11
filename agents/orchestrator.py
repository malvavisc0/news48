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
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Literal, Optional, cast

from agents.schedules import (
    _LOGS_DIR,
    _STATE_FILE,
    DEFAULT_SCHEDULES,
    AgentSchedule,
    RunningAgent,
    _duration_since,
    _is_process_alive,
    _tail_file,
)

logger = logging.getLogger(__name__)


class Orchestrator:
    """Python dispatcher that runs agents on a timer with predefined prompts.

    In daemon mode each agent is forked as a subprocess; the orchestrator
    tracks PIDs, polls for completion, and persists state to
    ``.orchestrator.json``.

    Agents with ``max_concurrent > 1`` (e.g. executor) may have multiple
    instances running simultaneously, each claiming a different plan.
    """

    def __init__(
        self,
        schedules: Optional[Dict[str, AgentSchedule]] = None,
    ):
        from dataclasses import replace

        self.schedules = schedules or {
            name: replace(s) for name, s in DEFAULT_SCHEDULES.items()
        }
        self.running: Dict[str, List[RunningAgent]] = {}

    def load_state(self) -> None:
        """Load schedule state from ``.orchestrator.json``.

        Restores ``last_run``, ``last_result``, and ``last_error`` for
        each schedule, and any previously running agent entries (their
        processes will be checked on the next tick).

        Handles both legacy (single-dict) and current (list) formats
        for the ``running`` section.
        """
        if _STATE_FILE.exists():
            try:
                data = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning(f"Could not load state: {exc}")
                data = {}

            # Restore schedule state
            for name, sched_data in data.get("schedules", {}).items():
                if name in self.schedules:
                    self.schedules[name].last_run = sched_data.get("last_run")
                    self.schedules[name].last_result = sched_data.get("last_result")
                    self.schedules[name].last_error = sched_data.get("last_error")

            # Restore running agent records (processes are gone after restart,
            # but we mark them as failed-unknown so we know they didn't finish)
            for name, run_data in data.get("running", {}).items():
                # Support both legacy (dict) and current (list) formats
                entries = run_data if isinstance(run_data, list) else [run_data]
                for entry in entries:
                    pid = entry.get("pid", 0)
                    if not _is_process_alive(pid):
                        # Process is gone -- mark as completed with unknown
                        if name in self.schedules:
                            self.schedules[name].last_run = entry.get("started_at")
                            self.schedules[name].last_result = "unknown"
                            self.schedules[name].last_error = (
                                "Process disappeared " "(orchestrator restarted?)"
                            )
                    else:
                        # Process is still running from a previous session
                        self.running.setdefault(name, []).append(
                            RunningAgent(
                                pid=pid,
                                agent_name=name,
                                started_at=entry.get("started_at", ""),
                                log_file=entry.get("log_file", ""),
                            )
                        )

        # Autonomous recovery pass: normalize/requeue stale executing plans
        # immediately on orchestrator startup.
        try:
            from agents.tools.planner import recover_stale_plans

            payload = json.loads(
                recover_stale_plans("Orchestrator startup recovery after restart")
            )
            if payload.get("error"):
                logger.warning("Plan recovery pass failed: %s", payload["error"])
            else:
                result = payload.get("result", {})
                logger.info(
                    "Plan recovery pass: scanned=%s normalized=%s requeued=%s",
                    result.get("scanned", 0),
                    result.get("normalized", 0),
                    result.get("requeued", 0),
                )
        except Exception as exc:
            logger.warning("Plan recovery startup hook failed: %s", exc)

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
        for name, instances in self.running.items():
            data["running"][name] = [
                {
                    "pid": r.pid,
                    "started_at": r.started_at,
                    "log_file": r.log_file,
                }
                for r in instances
            ]
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
        running_count = len(self.running.get(schedule.agent_name, []))
        if running_count >= schedule.max_concurrent:
            return False
        if schedule.last_run is None:
            return True
        try:
            last_run = datetime.fromisoformat(schedule.last_run)
            now = datetime.now(timezone.utc)
            interval = timedelta(minutes=schedule.interval_minutes)
            return (now - last_run) >= interval
        except (ValueError, TypeError):
            return True

    def _update_schedule(
        self, name: str, result: str, error: Optional[str] = None
    ) -> None:
        """Update schedule state after an agent run."""
        schedule = self.schedules.get(name)
        if schedule:
            schedule.last_run = datetime.now(timezone.utc).isoformat()
            schedule.last_result = result
            schedule.last_error = error

    async def run_agent(
        self,
        name: Literal["planner", "executor", "monitor"],
        task: str,
    ) -> Dict[str, Any]:
        """Run a specific agent inline (one-shot mode)."""
        _AGENT_MODULES = {
            "planner": "agents.planner",
            "executor": "agents.executor",
            "monitor": "agents.monitor",
        }
        if name not in _AGENT_MODULES:
            return {
                "agent": name,
                "result": None,
                "error": f"Unknown agent: {name}",
            }

        # Build task_context for skills composition
        task_context: dict = {}
        if name == "executor":
            # Peek at next plan family to load conditional executor skills
            try:
                from agents.tools.planner import peek_next_plan

                family = peek_next_plan()
                if family:
                    task_context["plan_family"] = family
            except Exception as exc:
                logger.warning("Failed to peek next plan family: %s", exc)

        import importlib

        module = importlib.import_module(_AGENT_MODULES[name])

        try:
            # Only pass task_context if non-empty for backward compatibility
            if task_context:
                result = await module.run(task, task_context)
            else:
                result = await module.run(task)
            self._update_schedule(name, "success")
            self.save_state()
            return {"agent": name, "result": result, "error": None}
        except Exception as e:
            logger.error(f"Agent {name} failed: {e}")
            self._update_schedule(name, "error", str(e))
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
            result = await self.run_agent(
                cast(
                    Literal["planner", "executor", "monitor"],
                    name,
                ),
                schedule.task_prompt,
            )
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
        instances = self.running.get(name, [])
        schedule = self.schedules.get(name)
        max_concurrent = schedule.max_concurrent if schedule else 1
        if len(instances) >= max_concurrent:
            pids = ", ".join(str(r.pid) for r in instances)
            logger.warning(
                f"Agent {name} at max concurrency " f"({max_concurrent}): PIDs {pids}"
            )
            return False

        _LOGS_DIR.mkdir(exist_ok=True)
        now = datetime.now(timezone.utc)
        timestamp = now.strftime("%Y%m%d-%H%M%S")
        # Add instance index to log filename for concurrent agents
        instance_idx = len(instances)
        if max_concurrent > 1:
            log_file = str(_LOGS_DIR / f"{name}-{timestamp}-{instance_idx}.log")
        else:
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
            self.running.setdefault(name, []).append(
                RunningAgent(
                    pid=proc.pid,
                    agent_name=name,
                    started_at=now.isoformat(),
                    log_file=log_file,
                    process=proc,
                )
            )
            logger.info(f"Forked agent {name} as PID {proc.pid} → {log_file}")
            return True
        except Exception as exc:
            logger.error(f"Failed to fork agent {name}: {exc}")
            return False

    def check_running(self) -> Dict[str, Dict[str, Any]]:
        """Poll running agent subprocesses for completion.

        For each completed process, updates the schedule state with
        the exit code and cleans up the running tracker.

        Returns:
            Dict of completion keys (``name`` or ``name:pid``) with results.
        """
        completed: Dict[str, Dict[str, Any]] = {}

        for name in list(self.running.keys()):
            instances = self.running[name]
            still_running: List[RunningAgent] = []

            for running in instances:
                proc = running.process
                pid = running.pid
                finished = False
                comp_info: Optional[Dict[str, Any]] = None

                # If we don't have a process handle (e.g., restored from
                # state after restart), check if the PID is still alive
                if proc is None:
                    if not _is_process_alive(pid):
                        finished = True
                        comp_info = {
                            "pid": pid,
                            "exit_code": None,
                            "result": "unknown",
                            "log_file": running.log_file,
                            "duration": _duration_since(running.started_at),
                        }
                else:
                    # Poll the process
                    exit_code = proc.poll()
                    if exit_code is not None:
                        finished = True
                        result = "success" if exit_code == 0 else "error"
                        error_msg = None

                        if exit_code != 0:
                            error_msg = _tail_file(running.log_file, lines=20)

                        comp_info = {
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

                if finished and comp_info:
                    # Use name:pid as key when multiple instances possible
                    comp_key = f"{name}:{pid}"
                    completed[comp_key] = comp_info
                else:
                    still_running.append(running)

            if still_running:
                self.running[name] = still_running
            else:
                self.running.pop(name, None)

        return completed

    def tick(self) -> Dict[str, Any]:
        """Run one orchestrator cycle.

        1. Check running processes for completion.
        2. Fork due agents (at most one new instance per agent per tick).
        3. Save state.

        Returns:
            Dict summarizing what happened this tick.
        """
        # 1. Check completed agents
        completed = self.check_running()

        # 2. Fork due agents (one-per-agent per tick to avoid burst-forking)
        forked: list[str] = []
        for name, schedule in self.schedules.items():
            if self._should_run(schedule):
                if self.fork_agent(name):
                    forked.append(name)

        # 3. Save state
        self.save_state()

        # Count total running instances
        total_running = sum(len(instances) for instances in self.running.values())

        return {
            "completed": completed,
            "forked": forked,
            "running": list(self.running.keys()),
            "running_total": total_running,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def start(self, tick_seconds: int = 60) -> None:
        """Run the orchestrator in a continuous loop."""
        logger.info(f"Orchestrator starting (tick every {tick_seconds}s)")
        self.load_state()

        try:
            while True:
                result = self.tick()
                n_c = len(result["completed"])
                n_f = len(result["forked"])
                n_r = result["running_total"]

                if n_c or n_f:
                    logger.info(
                        f"Tick: {n_f} forked, {n_c} completed, " f"{n_r} running"
                    )
                    for comp_key, info in result["completed"].items():
                        logger.info(
                            f"  {comp_key}: {info['result']} "
                            f"(exit={info.get('exit_code')}, "
                            f"duration={info.get('duration', '?')})"
                        )
                    for name in result["forked"]:
                        instances = self.running.get(name, [])
                        if instances:
                            logger.info(
                                f"  {name}: forked → " f"PID {instances[-1].pid}"
                            )

                time.sleep(tick_seconds)
        except KeyboardInterrupt:
            logger.info("Orchestrator stopped by user")
            self.save_state()

    def stop_agent(self, name: str) -> Dict[str, Any]:
        """Stop all running instances of an agent.

        Sends SIGTERM to each instance's process group, waits up to
        5 seconds, then SIGKILL if still alive. Releases any claimed
        plans for each stopped PID.
        """
        instances = self.running.get(name, [])
        if not instances:
            return {
                "stopped": [],
                "already_stopped": [name],
                "stopped_count": 0,
                "stopped_instances": [],
            }

        # Send SIGTERM to all instances
        for running in instances:
            try:
                os.killpg(os.getpgid(running.pid), signal.SIGTERM)
            except OSError:
                pass

        force_killed: set[int] = set()

        # Wait up to 5 seconds for all to die
        for _ in range(50):
            time.sleep(0.1)
            if all(not _is_process_alive(r.pid) for r in instances):
                break
        else:
            # Force kill any survivors
            for running in instances:
                if _is_process_alive(running.pid):
                    try:
                        os.killpg(os.getpgid(running.pid), signal.SIGKILL)
                        force_killed.add(running.pid)
                    except OSError:
                        pass

        # Release plans for each stopped PID
        from agents.tools.planner import release_plans_for_pid

        stopped_instances: list[dict[str, Any]] = []
        for running in instances:
            released = release_plans_for_pid(running.pid)
            stopped_instances.append(
                {
                    "pid": running.pid,
                    "started_at": running.started_at,
                    "log_file": running.log_file,
                    "signal": ("SIGKILL" if running.pid in force_killed else "SIGTERM"),
                    "released_plan_count": released["count"],
                    "released_plan_ids": released["released"],
                }
            )
            if released["count"]:
                logger.info(
                    "Released %d plan(s) from stopped %s (PID %d): %s",
                    released["count"],
                    name,
                    running.pid,
                    released["released"],
                )

        # Update schedule
        schedule = self.schedules.get(name)
        if schedule:
            schedule.last_run = instances[-1].started_at
            schedule.last_result = "stopped"
            schedule.last_error = "Stopped by user"

        self.running.pop(name, None)
        self.save_state()
        return {
            "stopped": [name],
            "already_stopped": [],
            "stopped_count": len(instances),
            "stopped_instances": stopped_instances,
        }

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

            instances = self.running.get(name, [])
            running_count = len(instances)
            running_info = [
                {
                    "pid": r.pid,
                    "started_at": r.started_at,
                    "log_file": r.log_file,
                }
                for r in instances
            ]

            status[name] = {
                "enabled": schedule.enabled,
                "interval_minutes": schedule.interval_minutes,
                "max_concurrent": schedule.max_concurrent,
                "last_run": schedule.last_run,
                "last_result": schedule.last_result,
                "last_error": schedule.last_error,
                "next_run": next_run,
                "task_prompt": schedule.task_prompt,
                "running": running_count > 0,
                "running_count": running_count,
                "running_info": running_info,
            }
        return status
