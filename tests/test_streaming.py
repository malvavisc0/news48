"""Tests for agents/streaming.py log formatting functions."""

from agents.streaming import _strip_prefix, format_log_line


class TestStripPrefix:
    """Tests for _strip_prefix helper function."""

    def test_removes_prefix_and_strips(self):
        """Should remove prefix and strip whitespace."""
        result = _strip_prefix(
            "Executing tool: update_plan", "Executing tool:"
        )
        assert result == "update_plan"

    def test_strips_leading_whitespace(self):
        """Should strip leading whitespace after prefix removal."""
        result = _strip_prefix(
            "Executing tool:   update_plan", "Executing tool:"
        )
        assert result == "update_plan"

    def test_strips_trailing_whitespace(self):
        """Should strip trailing whitespace."""
        result = _strip_prefix(
            "Executing tool: update_plan  ", "Executing tool:"
        )
        assert result == "update_plan"

    def test_empty_after_prefix(self):
        """Should handle empty string after prefix."""
        result = _strip_prefix("Executing tool:", "Executing tool:")
        assert result == ""

    def test_prefix_not_present(self):
        """Should return stripped message if prefix not present."""
        result = _strip_prefix("some message", "prefix:")
        assert result == "some message"


class TestFormatLogLine:
    """Tests for format_log_line function."""

    def test_executing_tool_with_reason(self):
        """Should format 'Executing tool' with reason."""
        line = (
            "2026-04-04 12:38:42.698 | INFO     | agents.pipeline:run:77 - "
            "Executing tool: update_plan. Reason: No downloaded articles found"
        )
        result = format_log_line(line)
        assert (
            result
            == "12:38 ⚙ Executing: update_plan (No downloaded articles found)"
        )

    def test_executing_tool_without_reason(self):
        """Should format 'Executing tool' without reason."""
        line = (
            "2026-04-04 12:38:42.698 | INFO     | agents.pipeline:run:77 - "
            "Executing tool: run_shell_command"
        )
        result = format_log_line(line)
        assert result == "12:38 ⚙ Executing: run_shell_command"

    def test_completed_execution(self):
        """Should format 'Completed execution of tool'."""
        line = (
            "2026-04-04 12:38:42.698 | INFO     | agents.pipeline:run:77 - "
            "Completed execution of tool: update_plan"
        )
        result = format_log_line(line)
        assert result == "12:38 ✔ Completed: update_plan"

    def test_system_error(self):
        """Should format 'System error while executing tool'."""
        line = (
            "2026-04-04 12:38:42.698 | ERROR    | agents.pipeline:run:77 - "
            "System error while executing tool: run_shell_command"
        )
        result = format_log_line(line)
        assert result == "12:38 ✖ Error: run_shell_command"

    def test_failed_execution_with_error(self):
        """Should format 'Unsuccessfully execution of the tool' with error."""
        line = (
            "2026-04-04 12:38:42.698 | ERROR    | agents.pipeline:run:77 - "
            "Unsuccessfully execution of the tool: parse. Error: Invalid JSON"
        )
        result = format_log_line(line)
        assert result == "12:38 ✖ Failed: parse (Invalid JSON)"

    def test_failed_execution_without_error(self):
        """Should format 'Unsuccessfully execution of the tool' without error."""
        line = (
            "2026-04-04 12:38:42.698 | ERROR    | agents.pipeline:run:77 - "
            "Unsuccessfully execution of the tool: parse"
        )
        result = format_log_line(line)
        assert result == "12:38 ✖ Failed: parse"

    def test_unknown_message_format(self):
        """Should return time + message for unknown formats."""
        line = (
            "2026-04-04 12:38:42.698 | INFO     | agents.pipeline:run:77 - "
            "Some other log message"
        )
        result = format_log_line(line)
        assert result == "12:38 Some other log message"

    def test_non_loguru_line(self):
        """Should return original line if it doesn't match loguru format."""
        line = "This is not a loguru line"
        result = format_log_line(line)
        assert result == "This is not a loguru line"

    def test_empty_line(self):
        """Should handle empty line."""
        result = format_log_line("")
        assert result == ""

    def test_different_time(self):
        """Should extract correct time."""
        line = (
            "2026-04-04 09:15:30.123 | INFO     | agents.pipeline:run:77 - "
            "Executing tool: fetch"
        )
        result = format_log_line(line)
        assert result == "09:15 ⚙ Executing: fetch"

    def test_different_log_levels(self):
        """Should work with different log levels (INFO, ERROR, WARNING)."""
        line_warning = (
            "2026-04-04 12:38:42.698 | WARNING  | agents.pipeline:run:77 - "
            "Executing tool: check"
        )
        result = format_log_line(line_warning)
        assert result == "12:38 ⚙ Executing: check"
