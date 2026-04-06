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
            "2026-04-04 12:38:42 [agents._run] "
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
            "2026-04-04 12:38:42 [agents._run] "
            "Executing tool: run_shell_command"
        )
        result = format_log_line(line)
        assert result == "12:38 ⚙ Executing: run_shell_command"

    def test_completed_execution(self):
        """Should format 'Completed execution of tool'."""
        line = (
            "2026-04-04 12:38:42 [agents._run] "
            "Completed execution of tool: update_plan"
        )
        result = format_log_line(line)
        assert result == "12:38 ✔ Completed: update_plan"

    def test_system_error(self):
        """Should format 'System error while executing tool'."""
        line = (
            "2026-04-04 12:38:42 [agents._run] "
            "System error while executing tool: run_shell_command"
        )
        result = format_log_line(line)
        assert result == "12:38 ✖ Error: run_shell_command"

    def test_failed_execution_with_error(self):
        """Should format 'Unsuccessfully execution of the tool' with error."""
        line = (
            "2026-04-04 12:38:42 [agents._run] "
            "Unsuccessfully execution of the tool: parse. Error: Invalid JSON"
        )
        result = format_log_line(line)
        assert result == "12:38 ✖ Failed: parse (Invalid JSON)"

    def test_failed_execution_without_error(self):
        """Should format 'Unsuccessfully execution' without error."""
        line = (
            "2026-04-04 12:38:42 [agents._run] "
            "Unsuccessfully execution of the tool: parse"
        )
        result = format_log_line(line)
        assert result == "12:38 ✖ Failed: parse"

    def test_unknown_message_format(self):
        """Should return time + message for unknown formats."""
        line = "2026-04-04 12:38:42 [agents._run] " "Some other log message"
        result = format_log_line(line)
        assert result == "12:38 Some other log message"

    def test_non_matching_line(self):
        """Should return original line if it doesn't match format."""
        line = "This is not a matching line"
        result = format_log_line(line)
        assert result == "This is not a matching line"

    def test_empty_line(self):
        """Should handle empty line."""
        result = format_log_line("")
        assert result == ""

    def test_different_time(self):
        """Should extract correct time."""
        line = "2026-04-04 09:15:30 [agents._run] " "Executing tool: fetch"
        result = format_log_line(line)
        assert result == "09:15 ⚙ Executing: fetch"

    def test_different_logger_names(self):
        """Should work with different logger names."""
        line = (
            "2026-04-04 12:38:42 [agents.orchestrator] "
            "Executing tool: check"
        )
        result = format_log_line(line)
        assert result == "12:38 ⚙ Executing: check"

    def test_httpx_line_compact(self):
        """Should compact httpx HTTP Request lines to minimal output."""
        line = (
            "2026-04-06 13:12:17 [httpx] HTTP Request: POST "
            "http://skynet.tago.lan:9090/v1/chat/completions "
            '"HTTP/1.1 200 OK"'
        )
        result = format_log_line(line)
        assert result == "13:12 🌐 API call"

    def test_httpx_line_different_method(self):
        """Should compact any httpx line regardless of HTTP method."""
        line = (
            "2026-04-06 09:00:01 [httpx] HTTP Request: GET "
            'http://example.com/api "HTTP/1.1 404 Not Found"'
        )
        result = format_log_line(line)
        assert result == "09:00 🌐 API call"

    def test_agent_stream_content(self):
        """Should format Agent stream lines with speech icon."""
        line = (
            "2026-04-06 13:12:18 [agents.streaming] "
            "Agent: The analysis shows three key findings."
        )
        result = format_log_line(line)
        assert result == "13:12 💬 The analysis shows three key findings."

    def test_agent_stream_short_content(self):
        """Should handle short Agent stream content."""
        line = "2026-04-06 08:30:00 [agents.streaming] Agent: Done."
        result = format_log_line(line)
        assert result == "08:30 💬 Done."
