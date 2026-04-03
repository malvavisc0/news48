"""Tests for the agent modules."""

from agents.orchestrator import AgentSchedule, Orchestrator

# ---------------------------------------------------------------------------
# Orchestrator tests (no LLM required)
# ---------------------------------------------------------------------------


class TestAgentSchedule:
    """Tests for AgentSchedule dataclass."""

    def test_default_values(self):
        schedule = AgentSchedule(
            agent_name="monitor",
            task_prompt="Check health",
            interval_minutes=15,
        )
        assert schedule.agent_name == "monitor"
        assert schedule.task_prompt == "Check health"
        assert schedule.interval_minutes == 15
        assert schedule.enabled is True
        assert schedule.last_run is None

    def test_custom_values(self):
        schedule = AgentSchedule(
            agent_name="pipeline",
            task_prompt="Run pipeline",
            interval_minutes=60,
            enabled=False,
            last_run="2024-01-01T00:00:00+00:00",
        )
        assert schedule.enabled is False
        assert schedule.last_run == "2024-01-01T00:00:00+00:00"


class TestOrchestrator:
    """Tests for the Orchestrator dispatcher."""

    def test_default_schedules(self):
        orchestrator = Orchestrator()
        assert "pipeline" in orchestrator.schedules
        assert "monitor" in orchestrator.schedules
        assert "reporter" in orchestrator.schedules
        assert "checker" in orchestrator.schedules

    def test_default_schedule_intervals(self):
        orchestrator = Orchestrator()
        assert orchestrator.schedules["pipeline"].interval_minutes == 60
        assert orchestrator.schedules["monitor"].interval_minutes == 15
        assert orchestrator.schedules["reporter"].interval_minutes == 1440
        assert orchestrator.schedules["checker"].interval_minutes == 360

    def test_should_run_when_never_run(self):
        schedule = AgentSchedule(
            agent_name="monitor",
            task_prompt="Check",
            interval_minutes=15,
        )
        orchestrator = Orchestrator()
        assert orchestrator._should_run(schedule) is True

    def test_should_not_run_when_disabled(self):
        schedule = AgentSchedule(
            agent_name="monitor",
            task_prompt="Check",
            interval_minutes=15,
            enabled=False,
        )
        orchestrator = Orchestrator()
        assert orchestrator._should_run(schedule) is False

    def test_should_not_run_when_interval_not_elapsed(self):
        from datetime import datetime, timedelta, timezone

        schedule = AgentSchedule(
            agent_name="monitor",
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
            agent_name="monitor",
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

        for name in ["pipeline", "monitor", "reporter", "checker"]:
            assert name in status
            assert "enabled" in status[name]
            assert "interval_minutes" in status[name]
            assert "last_run" in status[name]
            assert "next_run" in status[name]
            assert "task_prompt" in status[name]

    def test_get_status_disabled_agent(self):
        schedules = {
            "monitor": AgentSchedule(
                agent_name="monitor",
                task_prompt="Check",
                interval_minutes=15,
                enabled=False,
            ),
        }
        orchestrator = Orchestrator(schedules=schedules)
        status = orchestrator.get_status()
        assert status["monitor"]["next_run"] == "disabled"

    def test_get_status_never_run(self):
        schedules = {
            "monitor": AgentSchedule(
                agent_name="monitor",
                task_prompt="Check",
                interval_minutes=15,
            ),
        }
        orchestrator = Orchestrator(schedules=schedules)
        status = orchestrator.get_status()
        assert status["monitor"]["last_run"] is None
        assert status["monitor"]["next_run"] == "immediate"

    def test_run_agent_unknown(self):
        import asyncio

        orchestrator = Orchestrator()
        result = asyncio.run(orchestrator.run_agent("nonexistent", "do stuff"))
        assert result["agent"] == "nonexistent"
        assert result["error"] is not None
        assert "Unknown agent" in result["error"]

    def test_run_due_agents_none_due(self):
        import asyncio
        from datetime import datetime, timedelta, timezone

        schedules = {
            "monitor": AgentSchedule(
                agent_name="monitor",
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

    def test_run_due_agents_all_due(self):
        import asyncio

        schedules = {
            "monitor": AgentSchedule(
                agent_name="monitor",
                task_prompt="Check",
                interval_minutes=15,
            ),
        }
        orchestrator = Orchestrator(schedules=schedules)
        result = asyncio.run(orchestrator.run_due_agents())
        assert "monitor" in result["agents_run"]
        assert "timestamp" in result


# ---------------------------------------------------------------------------
# Agent module import tests (no LLM required)
# ---------------------------------------------------------------------------


class TestAgentImports:
    """Test that agent modules can be imported."""

    def test_import_pipeline(self):
        from agents.pipeline import get_agent, run

        assert callable(get_agent)
        assert callable(run)

    def test_import_monitor(self):
        from agents.monitor import get_agent, run

        assert callable(get_agent)
        assert callable(run)

    def test_import_reporter(self):
        from agents.reporter import get_agent, run

        assert callable(get_agent)
        assert callable(run)

    def test_import_checker(self):
        from agents.checker import get_agent, run

        assert callable(get_agent)
        assert callable(run)

    def test_import_orchestrator(self):
        from agents.orchestrator import Orchestrator

        assert Orchestrator is not None

    def test_import_parser(self):
        from agents.parser import NewsParsingResult, get_agent

        assert NewsParsingResult is not None
        assert callable(get_agent)

    def test_import_package(self):
        import agents

        assert hasattr(agents, "Orchestrator")
        assert hasattr(agents, "get_pipeline_agent")
        assert hasattr(agents, "get_monitor_agent")
        assert hasattr(agents, "get_reporter_agent")
        assert hasattr(agents, "get_checker_agent")
        assert hasattr(agents, "run_pipeline")
        assert hasattr(agents, "run_monitor")
        assert hasattr(agents, "run_reporter")
        assert hasattr(agents, "run_checker")
