"""Orchestrator -- Python dispatcher that runs agents on a schedule.

Supports two modes:
- One-shot: ``agents run`` checks what's due and runs agents inline.
- Daemon: ``agents start`` runs a continuous loop, forking each agent
  as an independent subprocess and tracking its outcome.
"""

import asyncio
import importlib
import json
import logging
import os
import signal
import subprocess
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import config
from agents.schedules import (
    DEFAULT_SCHEDULES,
    AgentSchedule,
    RunningAgent,
    _duration_since,
    _is_process_alive,
    _tail_file,
)

logger = logging.getLogger(__name__)

# Default command prefix for forking agent subprocesses.
# Override via the ORCHESTRATOR_CMD_PREFIX environment variable
# (space-separated, e.g. "python -m news48").
_DEFAULT_CMD_PREFIX = ["uv", "run", "news48"]

_AGENT_MODULES = {
    "sentinel": "agents.sentinel",
    "executor": "agents.executor",
    "parser": "agents.parser",
    "fact_checker": "agents.fact_checker",
}


def _get_cmd_prefix() -> List[str]:
    """Return the command prefix used to fork agent subprocesses.

    Reads ``ORCHESTRATOR_CMD_PREFIX`` from the environment; falls back
    to ``["uv", "run", "news48"]``.
    """
    override = os.environ.get("ORCHESTRATOR_CMD_PREFIX", "").strip()
    if override:
        return override.split()
    return list(_DEFAULT_CMD_PREFIX)


class Orchestrator:
    """Python dispatcher that runs agents on a timer with predefined prompts.

    In daemon mode each agent is forked as a subprocess; the orchestrator
    tracks PIDs, polls for completion, and persists state to
    ``data/orchestrator.json``.

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

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def load_state(self) -> None:
        """Load schedule state from ``data/orchestrator.json``.

        Restores ``last_run``, ``last_result``, and ``last_error`` for
        each schedule, and any previously running agent entries (their
        processes will be checked on the next tick).

        Only schedules present in the current ``DEFAULT_SCHEDULES`` are
        restored; stale entries from removed agents are silently ignored.
        """
        if not config.STATE_FILE.exists():
            return

        try:
            data = json.loads(config.STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not load state: %s", exc)
            return

        # Restore schedule state (only for known agents)
        for name, sched_data in data.get("schedules", {}).items():
            if name in self.schedules:
                self.schedules[name].last_run = sched_data.get("last_run")
                self.schedules[name].last_result = sched_data.get("last_result")
                self.schedules[name].last_error = sched_data.get("last_error")

        # Restore running agent records — list format only.
        # Processes are gone after restart so we mark them as
        # failed-unknown to indicate they didn't finish cleanly.
        for name, entries in data.get("running", {}).items():
            if not isinstance(entries, list):
                continue  # skip malformed entries
            for entry in entries:
                pid = entry.get("pid", 0)
                if not _is_process_alive(pid):
                    if name in self.schedules:
                        self.schedules[name].last_run = entry.get("started_at")
                        self.schedules[name].last_result = "unknown"
                        self.schedules[name].last_error = (
                            "Process disappeared (orchestrator restarted?)"
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

    def _recover_stale_plans(self) -> None:
        """Run an autonomous recovery pass for stale executing plans.

        Normalises and requeues plans that were left in ``executing``
        status after an orchestrator crash or restart.  Separated from
        :meth:`load_state` for clarity and testability.
        """
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

    def _recover_stale_articles(self) -> None:
        """Reset articles stuck in processing_status after a crash.

        Articles that were claimed for download or parsing but never
        completed (e.g. due to an orchestrator crash) will have their
        processing_status cleared so they can be re-claimed.
        """
        try:
            from config import Database
            from database.articles import release_stale_article_claims

            result = release_stale_article_claims(Database.path)
            if result.get("released"):
                logger.info(
                    "Article recovery pass: released %s stale claim(s)",
                    result["released"],
                )
        except Exception as exc:
            logger.warning("Article recovery startup hook failed: %s", exc)

    def _archive_old_plans(self) -> None:
        """Archive terminal plans older than 24 hours on startup.

        Moves completed/failed plans to ``data/plans/archive/`` so that
        ``claim_plan()`` and ``list_plans()`` scans remain fast.
        """
        try:
            from agents.tools.planner import archive_terminal_plans

            result = archive_terminal_plans()
            if result.get("archived"):
                logger.info(
                    "Plan archival: moved %s plan(s) to archive",
                    result["archived"],
                )
            if result.get("errors"):
                logger.warning(
                    "Plan archival: %s error(s) during archival",
                    result["errors"],
                )
        except Exception as exc:
            logger.warning("Plan archival startup hook failed: %s", exc)

    def _heal_plan_deadlocks(self) -> int:
        """Detect and repair campaign-parent deadlocks in pending plans.

        Runs every tick before forking agents.  Uses
        ``_normalize_plan_for_consistency`` to convert blocking
        ``parent_id`` references to campaigns into non-blocking
        ``campaign_id`` fields, and ``_auto_complete_campaigns`` to
        mark campaigns whose children are all terminal.

        Returns:
            Number of plans healed.
        """
        try:
            from agents.tools.planner import (
                _auto_complete_campaigns,
                _ensure_plans_dir,
                _normalize_plan_for_consistency,
                _write_plan,
            )

            plans_dir = _ensure_plans_dir()
            healed = 0
            for plan_file in plans_dir.glob("*.json"):
                try:
                    plan = json.loads(plan_file.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    continue
                if _normalize_plan_for_consistency(plan):
                    _write_plan(plan)
                    healed += 1

            auto_completed = _auto_complete_campaigns(plans_dir)
            healed += auto_completed

            if healed:
                logger.info(
                    "Plan deadlock heal: %d plan(s) repaired, "
                    "%d campaign(s) auto-completed",
                    healed - auto_completed,
                    auto_completed,
                )
            return healed
        except Exception as exc:
            logger.warning("Plan deadlock heal failed: %s", exc)
            return 0

    def _write_pid_file(self) -> None:
        """Write the orchestrator daemon's PID to ``data/orchestrator.pid``."""
        try:
            config.PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
        except OSError as exc:
            logger.warning("Failed to write PID file: %s", exc)

    def _remove_pid_file(self) -> None:
        """Remove the PID file on clean shutdown."""
        try:
            config.PID_FILE.unlink(missing_ok=True)
        except OSError:
            pass

    @classmethod
    def read_daemon_pid(cls) -> int | None:
        """Read the daemon PID from ``data/orchestrator.pid``.

        Returns the PID if the file exists and the process is alive,
        otherwise cleans up the stale file and returns ``None``.
        """
        if not config.PID_FILE.exists():
            return None
        try:
            pid = int(config.PID_FILE.read_text(encoding="utf-8").strip())
        except (ValueError, OSError):
            return None
        if _is_process_alive(pid):
            return pid
        # Stale PID file — process is dead
        try:
            config.PID_FILE.unlink(missing_ok=True)
        except OSError:
            pass
        return None

    @classmethod
    def stop_daemon(cls) -> dict[str, Any]:
        """Stop the orchestrator daemon process.

        Reads the PID from ``.orchestrator.pid``, sends SIGTERM, waits
        up to 10 seconds, then SIGKILL if still alive.

        Returns:
            Dict with ``daemon_pid``, ``stopped`` bool, ``signal`` used.
        """
        pid = cls.read_daemon_pid()
        if pid is None:
            return {"daemon_pid": None, "stopped": False, "signal": None}

        # Send SIGTERM
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            return {"daemon_pid": pid, "stopped": False, "signal": None}

        # Wait up to 10 seconds
        for _ in range(100):
            time.sleep(0.1)
            if not _is_process_alive(pid):
                try:
                    config.PID_FILE.unlink(missing_ok=True)
                except OSError:
                    pass
                return {
                    "daemon_pid": pid,
                    "stopped": True,
                    "signal": "SIGTERM",
                }

        # Force kill
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
        try:
            config.PID_FILE.unlink(missing_ok=True)
        except OSError:
            pass
        return {"daemon_pid": pid, "stopped": True, "signal": "SIGKILL"}

    def _write_heartbeat(self) -> None:
        """Write a heartbeat file with the current timestamp.

        External monitoring (systemd, Docker healthcheck, cron) can
        check this file's modification time to detect orchestrator
        crashes. If the heartbeat is older than 2× the tick interval,
        the orchestrator is likely dead.
        """
        try:
            config.HEARTBEAT_FILE.write_text(
                datetime.now(timezone.utc).isoformat(), encoding="utf-8"
            )
        except OSError as exc:
            logger.debug("Failed to write heartbeat file: %s", exc)

    def save_state(self) -> None:
        """Persist schedule state to ``data/orchestrator.json``."""
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
            config.STATE_FILE.write_text(
                json.dumps(data, indent=2, default=str),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.error("Could not save state: %s", exc)

    # ------------------------------------------------------------------
    # Scheduling helpers
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # One-shot (inline) mode
    # ------------------------------------------------------------------

    def _build_task_context(self, name: str) -> dict:
        """Build the ``task_context`` dict for a given agent.

        Returns an empty dict when no context is applicable.
        """
        task_context: dict = {}

        if name == "executor":
            try:
                from agents.tools.planner import peek_next_plan

                family = peek_next_plan()
                if family:
                    task_context["plan_family"] = family
            except Exception as exc:
                logger.warning("Failed to peek next plan family: %s", exc)

        elif name == "sentinel":
            try:
                email_ready = bool(
                    os.getenv("SMTP_HOST", "")
                    and os.getenv("SMTP_USER", "")
                    and os.getenv("SMTP_PASS", "")
                    and os.getenv("MONITOR_EMAIL_TO", "")
                )
                task_context["email_configured"] = email_ready

                # Add backlog context for conditional skills
                from commands._common import require_db
                from database import get_article_stats

                db_path = require_db()
                article_stats = get_article_stats(db_path)
                task_context["backlog_high"] = bool(
                    max(
                        int(article_stats.get("download_backlog") or 0),
                        int(article_stats.get("parse_backlog") or 0),
                    )
                    > 200
                )
            except Exception as exc:
                logger.warning("Failed to build sentinel task context: %s", exc)

        elif name == "fact_checker":
            # Fact-checker uses default skills; no special context needed.
            pass

        return task_context

    async def run_agent(
        self,
        name: str,
        task: str,
    ) -> Dict[str, Any]:
        """Run a specific agent inline (one-shot mode)."""
        if name not in _AGENT_MODULES:
            return {
                "agent": name,
                "result": None,
                "error": f"Unknown agent: {name}",
            }

        task_context = self._build_task_context(name)
        module = importlib.import_module(_AGENT_MODULES[name])

        try:
            # Parser uses a dedicated autonomous entry point;
            # all other agents accept task_context as an optional kwarg.
            if name == "parser":
                result = await module.run_autonomous(task)
            else:
                result = await module.run(task, task_context)
            self._update_schedule(name, "success")
            self.save_state()
            return {"agent": name, "result": result, "error": None}
        except Exception as e:
            logger.error("Agent %s failed: %s", name, e)
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
            result = await self.run_agent(name, schedule.task_prompt)
            results[name] = result
            agents_run.append(name)

        return {
            "agents_run": agents_run,
            "results": results,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------
    # Daemon (subprocess) mode
    # ------------------------------------------------------------------

    def fork_agent(self, name: str, task: Optional[str] = None) -> bool:
        """Fork an agent as an independent subprocess.

        Runs the agent CLI command in a new process, redirecting
        stdout/stderr to a log file.

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
                "Agent %s at max concurrency (%d): PIDs %s",
                name,
                max_concurrent,
                pids,
            )
            return False

        config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc)
        timestamp = now.strftime("%Y%m%d-%H%M%S")
        # Add instance index to log filename for concurrent agents
        instance_idx = len(instances)
        if max_concurrent > 1:
            log_file = str(config.LOGS_DIR / f"{name}-{timestamp}-{instance_idx}.log")
        else:
            log_file = str(config.LOGS_DIR / f"{name}-{timestamp}.log")

        cmd = _get_cmd_prefix() + ["agents", "run", "--agent", name, "--json"]
        if task:
            cmd.extend(["--task", task])

        log_fh = None
        try:
            log_fh = open(log_file, "w", encoding="utf-8")
            proc = subprocess.Popen(
                cmd,
                stdout=log_fh,
                stderr=subprocess.STDOUT,
                cwd=os.getcwd(),
                start_new_session=True,  # Detach from parent
            )
        except Exception as exc:
            logger.error("Failed to fork agent %s: %s", name, exc)
            return False
        finally:
            # Always close the parent's copy of the log fd; the child
            # inherited its own via the Popen file descriptor.
            if log_fh is not None:
                log_fh.close()

        self.running.setdefault(name, []).append(
            RunningAgent(
                pid=proc.pid,
                agent_name=name,
                started_at=now.isoformat(),
                log_file=log_file,
                process=proc,
            )
        )

        # Record the fork time so _should_run() doesn't re-trigger on
        # the very next tick for non-concurrent agents.
        self._update_schedule(name, "running")

        logger.info("Forked agent %s as PID %d → %s", name, proc.pid, log_file)
        return True

    def check_running(self) -> Dict[str, Dict[str, Any]]:
        """Poll running agent subprocesses for completion.

        For each completed process, updates the schedule state with
        the exit code and cleans up the running tracker.  Also enforces
        ``max_runtime_minutes`` — processes exceeding the limit are
        killed and marked as timed-out.

        Returns:
            Dict of completion keys (``name:pid``) with results.
        """
        completed: Dict[str, Dict[str, Any]] = {}
        now = datetime.now(timezone.utc)

        for name in list(self.running.keys()):
            instances = self.running[name]
            still_running: List[RunningAgent] = []
            schedule = self.schedules.get(name)
            max_runtime = timedelta(
                minutes=(schedule.max_runtime_minutes if schedule else 30)
            )

            for running in instances:
                proc = running.process
                pid = running.pid
                finished = False
                comp_info: Optional[Dict[str, Any]] = None

                # ---- timeout enforcement ----
                try:
                    started = datetime.fromisoformat(running.started_at)
                    elapsed = now - started
                except (ValueError, TypeError):
                    elapsed = timedelta()

                timed_out = elapsed >= max_runtime

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
                    elif timed_out:
                        # Kill the orphaned process that exceeded runtime
                        try:
                            os.killpg(os.getpgid(pid), signal.SIGKILL)
                        except OSError:
                            pass
                        finished = True
                        comp_info = {
                            "pid": pid,
                            "exit_code": None,
                            "result": "timeout",
                            "error": (
                                f"Killed after {elapsed} " f"(limit {max_runtime})"
                            ),
                            "log_file": running.log_file,
                            "duration": _duration_since(running.started_at),
                        }
                        logger.warning(
                            "Killed timed-out agent %s (PID %d) after %s",
                            name,
                            pid,
                            elapsed,
                        )
                else:
                    # Poll the process
                    exit_code = proc.poll()

                    if exit_code is not None:
                        # Reap the zombie immediately
                        try:
                            proc.wait(timeout=0)
                        except Exception:
                            pass

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
                        if schedule:
                            schedule.last_run = running.started_at
                            schedule.last_result = result
                            schedule.last_error = error_msg

                    elif timed_out:
                        # Process exceeded max_runtime — terminate it
                        try:
                            os.killpg(os.getpgid(pid), signal.SIGTERM)
                            proc.wait(timeout=5)
                        except Exception:
                            try:
                                os.killpg(os.getpgid(pid), signal.SIGKILL)
                                proc.wait(timeout=2)
                            except Exception:
                                pass

                        finished = True
                        comp_info = {
                            "pid": pid,
                            "exit_code": proc.poll(),
                            "result": "timeout",
                            "error": (
                                f"Killed after {elapsed} " f"(limit {max_runtime})"
                            ),
                            "log_file": running.log_file,
                            "duration": _duration_since(running.started_at),
                        }

                        if schedule:
                            schedule.last_run = running.started_at
                            schedule.last_result = "timeout"
                            schedule.last_error = comp_info["error"]

                        logger.warning(
                            "Killed timed-out agent %s (PID %d) after %s",
                            name,
                            pid,
                            elapsed,
                        )

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

        1. Check running processes for completion / timeout.
        2. Heal plan deadlocks (campaign-parent blocking).
        3. Fork due agents (at most one new instance per agent per tick).
        4. Save state.

        Returns:
            Dict summarizing what happened this tick.
        """
        # 1. Check completed agents
        completed = self.check_running()

        # 2. Heal plan deadlocks before forking agents
        healed = self._heal_plan_deadlocks()

        # 3. Fork due agents (one-per-agent per tick to avoid burst-forking)
        forked: list[str] = []
        for name, schedule in self.schedules.items():
            if self._should_run(schedule):
                if self.fork_agent(name):
                    forked.append(name)

        # 4. Save state
        self.save_state()

        # 5. Write heartbeat
        self._write_heartbeat()

        # Count total running instances
        total_running = sum(len(instances) for instances in self.running.values())

        return {
            "completed": completed,
            "healed": healed,
            "forked": forked,
            "running": list(self.running.keys()),
            "running_total": total_running,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------
    # Pipeline loops (async background tasks)
    # ------------------------------------------------------------------

    async def _feed_fetch_loop(self, interval: int = 60) -> None:
        """Continuously fetch feeds in a background loop."""
        from config import Database
        from database.feeds import get_all_feeds
        from helpers.feed import get_fetch_summary

        while True:
            try:
                feeds = get_all_feeds(Database.path)
                urls = [f["url"] for f in feeds]
                if not urls:
                    logger.warning("No feeds in database, skipping fetch cycle")
                    await asyncio.sleep(interval)
                    continue

                summary = await get_fetch_summary(
                    urls, delay=0.0, db_path=Database.path
                )
                logger.info(
                    "Feed fetch: %d successful, %d failed, %d articles",
                    len(summary.successful),
                    len(summary.failed),
                    sum(r.valid_articles_count for r in summary.successful),
                )
            except Exception as exc:
                logger.error("Feed fetch loop error: %s", exc)

            await asyncio.sleep(interval)

    async def _download_loop(self, interval: int = 30) -> None:
        """Continuously download articles in a background loop."""
        from commands.download import _download

        while True:
            try:
                result = await _download(limit=100, delay=0.0)
                if result.get("total", 0) > 0:
                    logger.info(
                        "Download loop: %d downloaded, %d failed",
                        result["downloaded"],
                        result["failed"],
                    )
                    # Trigger immediate parse after successful download
                    await self._trigger_parser_cycle()
            except Exception as exc:
                logger.error("Download loop error: %s", exc)

            await asyncio.sleep(interval)

    async def _trigger_parser_cycle(self) -> None:
        """Trigger an immediate parser cycle."""
        from agents.parser import run_autonomous

        result = await run_autonomous()
        logger.info("Immediate parse trigger: %s", result)

    def start(self, tick_seconds: int = 60) -> None:
        """Run the orchestrator in a continuous loop.

        Writes the daemon PID to ``.orchestrator.pid`` on startup and
        removes it on clean shutdown. External callers can use
        :meth:`read_daemon_pid` / :meth:`stop_daemon` to find and stop
        the daemon process.
        """
        logger.info("Orchestrator starting (tick every %ds)", tick_seconds)
        self._write_pid_file()
        self.load_state()
        self._recover_stale_plans()
        self._recover_stale_articles()
        self._archive_old_plans()

        async def _main_loop():
            # Launch pipeline loops as background tasks
            fetch_task = asyncio.create_task(self._feed_fetch_loop())
            download_task = asyncio.create_task(self._download_loop())

            try:
                while True:
                    # IMPORTANT: tick() is synchronous (uses subprocess.Popen).
                    # Run in executor to avoid blocking the async event loop.
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(None, self.tick)
                    n_c = len(result["completed"])
                    n_f = len(result["forked"])
                    n_r = result["running_total"]

                    if n_c or n_f:
                        parts = [
                            "Tick: forked=%d completed=%d running=%d" % (n_f, n_c, n_r)
                        ]
                        for comp_key, info in result["completed"].items():
                            parts.append(
                                "%s=%s/exit=%s/%s"
                                % (
                                    comp_key,
                                    info["result"],
                                    info.get("exit_code"),
                                    info.get("duration", "?"),
                                )
                            )
                        for name in result["forked"]:
                            instances = self.running.get(name, [])
                            if instances:
                                parts.append(
                                    "%s=forked/pid=%d" % (name, instances[-1].pid)
                                )
                        logger.info(" ".join(parts))

                    await asyncio.sleep(tick_seconds)
            finally:
                fetch_task.cancel()
                download_task.cancel()

        try:
            asyncio.run(_main_loop())
        except KeyboardInterrupt:
            logger.info("Orchestrator stopped by user")
            self.save_state()
        finally:
            self._remove_pid_file()

    # ------------------------------------------------------------------
    # Agent control
    # ------------------------------------------------------------------

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
        """Stop the daemon and all running agents.

        First stops the orchestrator daemon (if running) so it cannot
        re-fork agents, then stops all tracked agent subprocesses.
        """
        daemon_result = self.stop_daemon()

        stopped, already = [], []
        for name in list(self.running.keys()):
            result = self.stop_agent(name)
            stopped.extend(result["stopped"])
            already.extend(result["already_stopped"])
        return {
            "stopped": stopped,
            "already_stopped": already,
            "daemon": daemon_result,
        }

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
                "max_runtime_minutes": schedule.max_runtime_minutes,
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
