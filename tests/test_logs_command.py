"""Tests for logs command help text and validation."""

import json

from typer.testing import CliRunner

from news48.cli.main import app

runner = CliRunner()

VALID_AGENTS = ["executor", "sentinel", "fact_checker", "parser"]


def test_logs_list_invalid_agent_shows_current_choices():
    """Invalid --agent value produces error with current AGENT_CHOICES."""
    result = runner.invoke(app, ["logs", "list", "--agent", "planner", "--json"])
    assert result.exit_code == 1
    data = json.loads(result.output)
    assert "planner" in data["error"]
    for agent in VALID_AGENTS:
        assert agent in data["error"], f"Expected '{agent}' in error message"


def test_logs_files_invalid_agent_shows_current_choices():
    """Invalid --agent value on files subcommand uses current AGENT_CHOICES."""
    result = runner.invoke(app, ["logs", "files", "--agent", "monitor", "--json"])
    assert result.exit_code == 1
    data = json.loads(result.output)
    assert "monitor" in data["error"]
    for agent in VALID_AGENTS:
        assert agent in data["error"], f"Expected '{agent}' in error message"


def test_logs_list_valid_agents_accepted():
    """All current AGENT_CHOICES are accepted without error."""
    for agent in VALID_AGENTS:
        result = runner.invoke(app, ["logs", "list", "--agent", agent, "--json"])
        # Should not be a validation error
        # (may be empty results, which is fine)
        if result.output.strip():
            data = json.loads(result.output)
            if isinstance(data, dict):
                assert "Invalid agent type" not in data.get("error", "")
