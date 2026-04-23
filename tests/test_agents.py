"""Non-LLM tests for agent run helpers and Dramatiq architecture."""

from news48.core.agents._run import _is_empty_claim_result, _is_substantive_result


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
