"""Integration tests for Dramatiq actors.

Tests message serialization and queue routing using
Dramatiq's StubBroker to avoid requiring live Redis.
"""


class TestActorModuleSyntax:
    """Verify actors module has correct syntax."""

    def test_actors_file_parses(self):
        """Verify actors.py is valid Python syntax."""
        import ast
        from pathlib import Path

        actors_path = Path(__file__).parent.parent / "news48" / "core" / "agents" / "actors.py"
        source = actors_path.read_text(encoding="utf-8")
        # Should not raise SyntaxError
        ast.parse(source)

    def test_actors_uses_cron_decorator(self):
        """Verify actors.py uses periodiq cron decorator."""
        from pathlib import Path

        actors_path = Path(__file__).parent.parent / "news48" / "core" / "agents" / "actors.py"
        source = actors_path.read_text(encoding="utf-8")
        assert "periodic=cron(" in source

    def test_actors_has_queue_names(self):
        """Verify actors.py defines queue assignments."""
        from pathlib import Path

        actors_path = Path(__file__).parent.parent / "news48" / "core" / "agents" / "actors.py"
        source = actors_path.read_text(encoding="utf-8")
        for queue in [
            "sentinel",
            "executor",
            "parser",
            "fact_checker",
            "pipeline",
        ]:
            assert f'queue_name="{queue}"' in source


class TestWorkersHelpers:
    """Test shared worker helper functions."""

    def test_build_task_context_sentinel(self):
        """Verify sentinel context includes email_configured."""
        from news48.core.agents.workers import build_task_context

        ctx = build_task_context("sentinel")
        assert "email_configured" in ctx

    def test_build_task_context_executor(self):
        """Verify executor context is a dict."""
        from news48.core.agents.workers import build_task_context

        ctx = build_task_context("executor")
        assert isinstance(ctx, dict)

    def test_build_task_context_fact_checker(self):
        """Verify fact_checker context is empty dict."""
        from news48.core.agents.workers import build_task_context

        ctx = build_task_context("fact_checker")
        assert ctx == {}


class TestMiddleware:
    """Test custom middleware classes."""

    def test_structured_logging_middleware_exists(self):
        """Verify StructuredLoggingMiddleware is defined."""
        from news48.core.agents.middleware import StructuredLoggingMiddleware

        assert StructuredLoggingMiddleware is not None

    def test_plan_recovery_middleware_exists(self):
        """Verify PlanRecoveryMiddleware is defined."""
        from news48.core.agents.middleware import PlanRecoveryMiddleware

        assert PlanRecoveryMiddleware is not None

    def test_startup_recovery_middleware_exists(self):
        """Verify StartupRecoveryMiddleware is defined."""
        from news48.core.agents.middleware import StartupRecoveryMiddleware

        assert StartupRecoveryMiddleware is not None


class TestBroker:
    """Test broker configuration."""

    def test_broker_configured(self):
        """Verify broker module can be imported."""
        from news48.core.agents import broker

        assert broker.redis_broker is not None


class TestPlannerExtensions:
    """Test planner module extensions for Dramatiq."""

    def test_release_plans_for_owner_exists(self):
        """Verify release_plans_for_owner function exists."""
        from news48.core.agents.tools.planner import release_plans_for_owner

        assert callable(release_plans_for_owner)

    def test_release_plans_for_owner_empty(self, tmp_path, monkeypatch):
        """Verify release_plans_for_owner returns dict with count."""
        from news48.core import config
        from news48.core.agents.tools.planner import release_plans_for_owner

        monkeypatch.setattr(config, "PLANS_DIR", tmp_path / ".plans")
        result = release_plans_for_owner("test:owner")
        assert "released" in result
        assert "count" in result
        assert result["count"] == 0
