"""Unit tests for Dramatiq workers and middleware.

Tests helper functions and middleware classes without
requiring actor registration (which causes duplicate
registration errors in pytest's isolated test environment).
"""


class TestWorkersHelpers:
    """Test shared worker helper functions."""

    def test_build_task_context_sentinel(self):
        """Verify sentinel context includes email_configured."""
        from agents.workers import build_task_context

        ctx = build_task_context("sentinel")
        assert "email_configured" in ctx

    def test_build_task_context_executor(self):
        """Verify executor context may include plan_family."""
        from agents.workers import build_task_context

        ctx = build_task_context("executor")
        assert isinstance(ctx, dict)

    def test_build_task_context_fact_checker(self):
        """Verify fact_checker context is empty dict."""
        from agents.workers import build_task_context

        ctx = build_task_context("fact_checker")
        assert ctx == {}

    def test_build_task_context_unknown(self):
        """Verify unknown agent returns empty dict."""
        from agents.workers import build_task_context

        ctx = build_task_context("unknown_agent")
        assert ctx == {}


class TestMiddleware:
    """Test custom middleware classes."""

    def test_structured_logging_middleware_exists(self):
        """Verify StructuredLoggingMiddleware is defined."""
        from agents.middleware import StructuredLoggingMiddleware

        assert StructuredLoggingMiddleware is not None

    def test_plan_recovery_middleware_exists(self):
        """Verify PlanRecoveryMiddleware is defined."""
        from agents.middleware import PlanRecoveryMiddleware

        assert PlanRecoveryMiddleware is not None

    def test_startup_recovery_middleware_exists(self):
        """Verify StartupRecoveryMiddleware is defined."""
        from agents.middleware import StartupRecoveryMiddleware

        assert StartupRecoveryMiddleware is not None


class TestBroker:
    """Test broker configuration."""

    def test_broker_configured(self):
        """Verify broker module can be imported."""
        from agents import broker

        assert broker.redis_broker is not None


class TestActorModuleSyntax:
    """Verify actors module has correct syntax (no import)."""

    def test_actors_file_parses(self):
        """Verify actors.py is valid Python syntax."""
        import ast
        from pathlib import Path

        actors_path = Path(__file__).parent.parent / "agents" / "actors.py"
        source = actors_path.read_text(encoding="utf-8")
        # Should not raise SyntaxError
        ast.parse(source)

    def test_actors_has_expected_functions(self):
        """Verify actors.py defines expected function names."""
        import ast
        from pathlib import Path

        actors_path = Path(__file__).parent.parent / "agents" / "actors.py"
        source = actors_path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        function_names = [
            node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
        ]

        expected = [
            "sentinel_cycle",
            "scheduled_sentinel",
            "executor_cycle",
            "scheduled_executor",
            "parser_cycle",
            "parse_single_article",
            "scheduled_parser",
            "fact_check_cycle",
            "scheduled_fact_checker",
            "feed_fetch_cycle",
            "download_cycle",
            "scheduled_feed_fetch",
            "scheduled_download",
            "heal_plan_deadlocks",
        ]
        for name in expected:
            assert name in function_names, f"Missing function: {name}"
