"""Non-LLM tests for orchestrator scheduling behavior."""

import json
from datetime import datetime, timezone
from typing import Any, cast

import config
from agents import orchestrator as orchestrator_module
from agents._run import _is_empty_claim_result, _is_substantive_result
from agents.orchestrator import Orchestrator
from agents.schedules import AgentSchedule, RunningAgent
from agents.tools import planner as planner_tools


class TestAgentSchedule:
    """Tests for [`AgentSchedule`](agents/orchestrator.py:27)."""

    def test_default_values(self):
        schedule = AgentSchedule(
            agent_name="planner",
            task_prompt="Check health",
            interval_minutes=15,
        )
        assert schedule.agent_name == "planner"
        assert schedule.task_prompt == "Check health"
        assert schedule.interval_minutes == 15
        assert schedule.enabled is True
        assert schedule.last_run is None

    def test_custom_values(self):
        schedule = AgentSchedule(
            agent_name="planner",
            task_prompt="Run planner",
            interval_minutes=60,
            enabled=False,
            last_run="2024-01-01T00:00:00+00:00",
        )
        assert schedule.enabled is False
        assert schedule.last_run == "2024-01-01T00:00:00+00:00"


class TestOrchestrator:
    """Pure scheduler tests that do not import LLM-backed agent modules."""

    def test_default_schedules(self):
        orchestrator = Orchestrator()
        assert "sentinel" in orchestrator.schedules
        assert "executor" in orchestrator.schedules
        assert "parser" in orchestrator.schedules
        assert "fact_checker" in orchestrator.schedules

    def test_default_schedule_intervals(self):
        orchestrator = Orchestrator()
        assert orchestrator.schedules["sentinel"].interval_minutes == 5
        assert orchestrator.schedules["executor"].interval_minutes == 1
        assert orchestrator.schedules["parser"].interval_minutes == 1
        assert orchestrator.schedules["fact_checker"].interval_minutes == 5

    def test_should_run_when_never_run(self):
        schedule = AgentSchedule(
            agent_name="planner",
            task_prompt="Check",
            interval_minutes=15,
        )
        orchestrator = Orchestrator()
        assert orchestrator._should_run(schedule) is True

    def test_should_not_run_when_disabled(self):
        schedule = AgentSchedule(
            agent_name="planner",
            task_prompt="Check",
            interval_minutes=15,
            enabled=False,
        )
        orchestrator = Orchestrator()
        assert orchestrator._should_run(schedule) is False

    def test_should_not_run_when_interval_not_elapsed(self):
        from datetime import datetime, timedelta, timezone

        schedule = AgentSchedule(
            agent_name="planner",
            task_prompt="Check",
            interval_minutes=15,
            last_run=(datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
        )
        orchestrator = Orchestrator()
        assert orchestrator._should_run(schedule) is False

    def test_should_run_when_interval_elapsed(self):
        from datetime import datetime, timedelta, timezone

        schedule = AgentSchedule(
            agent_name="planner",
            task_prompt="Check",
            interval_minutes=15,
            last_run=(datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat(),
        )
        orchestrator = Orchestrator()
        assert orchestrator._should_run(schedule) is True

    def test_get_status_structure(self):
        orchestrator = Orchestrator()
        status = orchestrator.get_status()

        for name in ["sentinel", "executor", "parser", "fact_checker"]:
            assert name in status
            assert "enabled" in status[name]
            assert "interval_minutes" in status[name]
            assert "last_run" in status[name]
            assert "next_run" in status[name]
            assert "task_prompt" in status[name]

    def test_get_status_disabled_agent(self):
        schedules = {
            "sentinel": AgentSchedule(
                agent_name="sentinel",
                task_prompt="Check",
                interval_minutes=15,
                enabled=False,
            ),
        }
        orchestrator = Orchestrator(schedules=schedules)
        status = orchestrator.get_status()
        assert status["sentinel"]["next_run"] == "disabled"

    def test_get_status_never_run(self):
        schedules = {
            "sentinel": AgentSchedule(
                agent_name="sentinel",
                task_prompt="Check",
                interval_minutes=15,
            ),
        }
        orchestrator = Orchestrator(schedules=schedules)
        status = orchestrator.get_status()
        assert status["sentinel"]["last_run"] is None
        assert status["sentinel"]["next_run"] == "immediate"

    def test_run_agent_unknown(self):
        import asyncio

        orchestrator = Orchestrator()
        result = asyncio.run(
            orchestrator.run_agent(
                cast(Any, "nonexistent"),
                "do stuff",
            )
        )
        assert result["agent"] == "nonexistent"
        assert result["error"] is not None
        assert "Unknown agent" in result["error"]

    def test_run_due_agents_none_due(self):
        import asyncio
        from datetime import datetime, timedelta, timezone

        schedules = {
            "sentinel": AgentSchedule(
                agent_name="sentinel",
                task_prompt="Check",
                interval_minutes=15,
                last_run=(
                    datetime.now(timezone.utc) - timedelta(minutes=1)
                ).isoformat(),
            ),
        }
        orchestrator = Orchestrator(schedules=schedules)
        result = asyncio.run(orchestrator.run_due_agents())
        assert result["agents_run"] == []
        assert result["results"] == {}

    def test_load_state_runs_recovery_without_state_file(self, tmp_path, monkeypatch):
        state_file = tmp_path / "orchestrator.json"
        monkeypatch.setattr(config, "STATE_FILE", state_file)

        calls = []

        def _fake_recover(reason: str) -> str:
            calls.append(reason)
            return json.dumps(
                {
                    "result": {
                        "scanned": 0,
                        "normalized": 0,
                        "requeued": 0,
                    },
                    "error": "",
                }
            )

        monkeypatch.setattr(planner_tools, "recover_stale_plans", _fake_recover)

        orchestrator = Orchestrator()
        orchestrator.load_state()
        orchestrator._recover_stale_plans()

        assert len(calls) == 1
        assert "startup" in calls[0].lower()

    def test_load_state_marks_disappeared_process_and_runs_recovery(
        self, tmp_path, monkeypatch
    ):
        state_file = tmp_path / "orchestrator.json"
        state_file.write_text(
            json.dumps(
                {
                    "schedules": {},
                    "running": {
                        "sentinel": [
                            {
                                "pid": 123456,
                                "started_at": "2026-01-01T00:00:00+00:00",
                                "log_file": "data/logs/sentinel.log",
                            }
                        ]
                    },
                }
            ),
            encoding="utf-8",
        )

        monkeypatch.setattr(config, "STATE_FILE", state_file)
        monkeypatch.setattr(orchestrator_module, "_is_process_alive", lambda _p: False)

        called = {"value": False}

        def _fake_recover(_reason: str) -> str:
            called["value"] = True
            return json.dumps(
                {
                    "result": {
                        "scanned": 1,
                        "normalized": 0,
                        "requeued": 1,
                    },
                    "error": "",
                }
            )

        monkeypatch.setattr(planner_tools, "recover_stale_plans", _fake_recover)

        orchestrator = Orchestrator()
        orchestrator.load_state()
        orchestrator._recover_stale_plans()

        assert called["value"] is True
        schedule = orchestrator.schedules["sentinel"]
        assert schedule.last_result == "unknown"
        assert "disappeared" in (schedule.last_error or "").lower()

    def test_tick_forks_at_most_one_instance_per_agent_per_tick(self):
        schedules = {
            "executor": AgentSchedule(
                agent_name="executor",
                task_prompt="Run executor",
                interval_minutes=1,
                max_concurrent=3,
            )
        }
        orchestrator = Orchestrator(schedules=schedules)

        calls = {"forks": 0}

        orchestrator.check_running = lambda: {}

        def _fake_fork(name: str, task=None):
            calls["forks"] += 1
            return True

        orchestrator.fork_agent = _fake_fork
        orchestrator.save_state = lambda: None
        # Executor precondition must report claimable plans exist
        orchestrator._agent_precondition_met = lambda name: True

        result = orchestrator.tick()

        assert calls["forks"] == 1
        assert result["forked"] == ["executor"]

    def test_run_agent_inline_ignores_daemon_running_slots(self, tmp_path, monkeypatch):
        import asyncio
        import importlib

        monkeypatch.setattr(config, "STATE_FILE", tmp_path / "orchestrator.json")

        orchestrator = Orchestrator()
        orchestrator.running["executor"] = [
            RunningAgent(
                pid=111,
                agent_name="executor",
                started_at=datetime.now(timezone.utc).isoformat(),
                log_file="data/logs/executor-a.log",
            ),
            RunningAgent(
                pid=222,
                agent_name="executor",
                started_at=datetime.now(timezone.utc).isoformat(),
                log_file="data/logs/executor-b.log",
            ),
            RunningAgent(
                pid=333,
                agent_name="executor",
                started_at=datetime.now(timezone.utc).isoformat(),
                log_file="data/logs/executor-c.log",
            ),
        ]

        class _FakeModule:
            @staticmethod
            async def run(task: str, task_context: dict | None = None):
                return f"ok:{task}"

        monkeypatch.setattr(importlib, "import_module", lambda _name: _FakeModule)

        result = asyncio.run(orchestrator.run_agent("executor", "inline"))
        assert result["error"] is None
        assert result["result"] == "ok:inline"

    def test_stop_agent_returns_instance_details_and_release_counts(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(config, "STATE_FILE", tmp_path / "orchestrator.json")

        orchestrator = Orchestrator(
            schedules={
                "executor": AgentSchedule(
                    agent_name="executor",
                    task_prompt="Run",
                    interval_minutes=1,
                    max_concurrent=3,
                )
            }
        )

        orchestrator.running["executor"] = [
            RunningAgent(
                pid=101,
                agent_name="executor",
                started_at="2026-01-01T00:00:00+00:00",
                log_file="data/logs/executor-101.log",
            ),
            RunningAgent(
                pid=202,
                agent_name="executor",
                started_at="2026-01-01T00:00:01+00:00",
                log_file="data/logs/executor-202.log",
            ),
        ]

        monkeypatch.setattr(
            orchestrator_module, "_is_process_alive", lambda _pid: False
        )
        monkeypatch.setattr(orchestrator_module.os, "killpg", lambda _pgid, _sig: None)
        monkeypatch.setattr(orchestrator_module.os, "getpgid", lambda pid: pid)
        monkeypatch.setattr(orchestrator_module.time, "sleep", lambda _s: None)

        released_calls = []

        def _fake_release(pid: int):
            released_calls.append(pid)
            return {
                "released": [f"plan-{pid}"],
                "count": 1,
            }

        monkeypatch.setattr(planner_tools, "release_plans_for_pid", _fake_release)

        result = orchestrator.stop_agent("executor")

        assert result["stopped"] == ["executor"]
        assert result["stopped_count"] == 2
        assert len(result["stopped_instances"]) == 2
        assert {entry["pid"] for entry in result["stopped_instances"]} == {
            101,
            202,
        }
        assert all(
            entry["released_plan_count"] == 1 for entry in result["stopped_instances"]
        )
        assert released_calls == [101, 202]

    def test_stop_agent_not_running_returns_empty_instance_payload(self):
        orchestrator = Orchestrator()
        result = orchestrator.stop_agent("executor")

        assert result["stopped"] == []
        assert result["already_stopped"] == ["executor"]
        assert result["stopped_count"] == 0
        assert result["stopped_instances"] == []

    def test_executor_precondition_skips_when_no_claimable_plans(self):
        """Executor should not be forked when peek_next_plan returns None."""
        schedules = {
            "executor": AgentSchedule(
                agent_name="executor",
                task_prompt="Run executor",
                interval_minutes=1,
                max_concurrent=3,
            )
        }
        orchestrator = Orchestrator(schedules=schedules)
        orchestrator.check_running = lambda: {}
        orchestrator.save_state = lambda: None

        # No claimable plans
        monkeypatch_value = {"peek": None}

        def _fake_precondition(name):
            if name == "executor":
                return monkeypatch_value["peek"] is not None
            return True

        orchestrator._agent_precondition_met = _fake_precondition

        calls = {"forks": 0}

        def _fake_fork(name, task=None):
            calls["forks"] += 1
            return True

        orchestrator.fork_agent = _fake_fork

        result = orchestrator.tick()

        assert calls["forks"] == 0
        assert result["forked"] == []

    def test_executor_precondition_allows_when_plans_exist(self):
        """Executor should be forked when peek_next_plan returns a family."""
        schedules = {
            "executor": AgentSchedule(
                agent_name="executor",
                task_prompt="Run executor",
                interval_minutes=1,
                max_concurrent=3,
            )
        }
        orchestrator = Orchestrator(schedules=schedules)
        orchestrator.check_running = lambda: {}
        orchestrator.save_state = lambda: None

        def _fake_precondition(name):
            if name == "executor":
                return True  # claimable plans exist
            return True

        orchestrator._agent_precondition_met = _fake_precondition

        calls = {"forks": 0}

        def _fake_fork(name, task=None):
            calls["forks"] += 1
            return True

        orchestrator.fork_agent = _fake_fork

        result = orchestrator.tick()

        assert calls["forks"] == 1
        assert result["forked"] == ["executor"]

    def test_non_executor_agents_always_pass_precondition(self):
        """Non-executor agents should always pass the precondition check."""
        orchestrator = Orchestrator()
        assert orchestrator._agent_precondition_met("sentinel") is True
        assert orchestrator._agent_precondition_met("parser") is True
        assert orchestrator._agent_precondition_met("fact_checker") is True

    def test_executor_precondition_with_peek_next_plan(self, monkeypatch):
        """_agent_precondition_met calls peek_next_plan for executor."""
        orchestrator = Orchestrator()

        # When peek returns None, executor should be blocked
        monkeypatch.setattr(planner_tools, "peek_next_plan", lambda: None)
        assert orchestrator._agent_precondition_met("executor") is False

        # When peek returns a family, executor should be allowed
        monkeypatch.setattr(planner_tools, "peek_next_plan", lambda: "fetch")
        assert orchestrator._agent_precondition_met("executor") is True

    def test_executor_precondition_fails_open_on_error(self, monkeypatch):
        """_agent_precondition_met returns True if peek_next_plan raises."""

        def _boom():
            raise RuntimeError("plans dir missing")

        monkeypatch.setattr(planner_tools, "peek_next_plan", _boom)
        orchestrator = Orchestrator()
        assert orchestrator._agent_precondition_met("executor") is True


class TestRunLoopHelpers:
    """Tests for _run.py circuit-breaker helper functions."""

    # --- _is_empty_claim_result ---

    def test_empty_claim_structured_no_eligible(self):
        output = {
            "result": {
                "status": "no_eligible_plans",
                "message": (
                    "No eligible pending plans found. " "You must exit immediately."
                ),
            },
            "error": "",
        }
        assert _is_empty_claim_result(output) is True

    def test_empty_claim_legacy_empty_string(self):
        """Backward compat: old-style empty string result is also empty."""
        output = {"result": "", "error": ""}
        assert _is_empty_claim_result(output) is True

    def test_empty_claim_none_result(self):
        output = {"result": None, "error": ""}
        assert _is_empty_claim_result(output) is True

    def test_empty_claim_real_plan(self):
        output = {
            "result": {
                "plan_id": "abc-123",
                "task": "Fetch feeds",
                "status": "executing",
            },
            "error": "",
        }
        assert _is_empty_claim_result(output) is False

    # --- _is_substantive_result ---

    def test_substantive_with_real_plan(self):
        output = {
            "result": {
                "plan_id": "abc-123",
                "task": "Fetch feeds",
                "status": "executing",
            },
            "error": "",
        }
        assert _is_substantive_result(output) is True

    def test_hollow_empty_string(self):
        output = {"result": "", "error": ""}
        assert _is_substantive_result(output) is False

    def test_hollow_none(self):
        output = {"result": None, "error": ""}
        assert _is_substantive_result(output) is False

    def test_hollow_no_eligible_plans(self):
        output = {
            "result": {
                "status": "no_eligible_plans",
                "message": "No eligible pending plans found.",
            },
            "error": "",
        }
        assert _is_substantive_result(output) is False

    def test_substantive_shell_command_result(self):
        output = {
            "result": {
                "return_code": 0,
                "stdout": "OK",
                "stderr": "",
                "execution_time": 1.2,
            },
            "error": "",
        }
        assert _is_substantive_result(output) is True
