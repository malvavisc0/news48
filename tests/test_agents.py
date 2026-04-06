"""Non-LLM tests for orchestrator scheduling behavior."""

import json
from typing import Any, cast

from agents import orchestrator as orchestrator_module
from agents.orchestrator import Orchestrator
from agents.schedules import AgentSchedule
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
        assert "planner" in orchestrator.schedules
        assert "executor" in orchestrator.schedules
        assert "monitor" in orchestrator.schedules

    def test_default_schedule_intervals(self):
        orchestrator = Orchestrator()
        assert orchestrator.schedules["planner"].interval_minutes == 1
        assert orchestrator.schedules["executor"].interval_minutes == 1
        assert orchestrator.schedules["monitor"].interval_minutes == 1440

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
            last_run=(
                datetime.now(timezone.utc) - timedelta(minutes=5)
            ).isoformat(),
        )
        orchestrator = Orchestrator()
        assert orchestrator._should_run(schedule) is False

    def test_should_run_when_interval_elapsed(self):
        from datetime import datetime, timedelta, timezone

        schedule = AgentSchedule(
            agent_name="planner",
            task_prompt="Check",
            interval_minutes=15,
            last_run=(
                datetime.now(timezone.utc) - timedelta(minutes=20)
            ).isoformat(),
        )
        orchestrator = Orchestrator()
        assert orchestrator._should_run(schedule) is True

    def test_get_status_structure(self):
        orchestrator = Orchestrator()
        status = orchestrator.get_status()

        for name in ["planner", "executor", "monitor"]:
            assert name in status
            assert "enabled" in status[name]
            assert "interval_minutes" in status[name]
            assert "last_run" in status[name]
            assert "next_run" in status[name]
            assert "task_prompt" in status[name]

    def test_get_status_disabled_agent(self):
        schedules = {
            "planner": AgentSchedule(
                agent_name="planner",
                task_prompt="Check",
                interval_minutes=15,
                enabled=False,
            ),
        }
        orchestrator = Orchestrator(schedules=schedules)
        status = orchestrator.get_status()
        assert status["planner"]["next_run"] == "disabled"

    def test_get_status_never_run(self):
        schedules = {
            "planner": AgentSchedule(
                agent_name="planner",
                task_prompt="Check",
                interval_minutes=15,
            ),
        }
        orchestrator = Orchestrator(schedules=schedules)
        status = orchestrator.get_status()
        assert status["planner"]["last_run"] is None
        assert status["planner"]["next_run"] == "immediate"

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
            "planner": AgentSchedule(
                agent_name="planner",
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

    def test_load_state_runs_recovery_without_state_file(
        self, tmp_path, monkeypatch
    ):
        state_file = tmp_path / ".orchestrator.json"
        monkeypatch.setattr(orchestrator_module, "_STATE_FILE", state_file)

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

        monkeypatch.setattr(
            planner_tools, "recover_stale_plans", _fake_recover
        )

        orchestrator = Orchestrator()
        orchestrator.load_state()

        assert len(calls) == 1
        assert "startup" in calls[0].lower()

    def test_load_state_marks_disappeared_process_and_runs_recovery(
        self, tmp_path, monkeypatch
    ):
        state_file = tmp_path / ".orchestrator.json"
        state_file.write_text(
            json.dumps(
                {
                    "schedules": {},
                    "running": {
                        "planner": {
                            "pid": 123456,
                            "started_at": "2026-01-01T00:00:00+00:00",
                            "log_file": ".logs/planner.log",
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

        monkeypatch.setattr(orchestrator_module, "_STATE_FILE", state_file)
        monkeypatch.setattr(
            orchestrator_module, "_is_process_alive", lambda _p: False
        )

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

        monkeypatch.setattr(
            planner_tools, "recover_stale_plans", _fake_recover
        )

        orchestrator = Orchestrator()
        orchestrator.load_state()

        assert called["value"] is True
        schedule = orchestrator.schedules["planner"]
        assert schedule.last_result == "unknown"
        assert "disappeared" in (schedule.last_error or "").lower()
