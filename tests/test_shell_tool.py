import sys

from agents.tools.shell import _prepare_shell_command


def test_prepare_shell_command_binds_news48_to_current_interpreter():
    argv, resolved = _prepare_shell_command("news48 stats --json")

    assert argv[:2] == ["/bin/bash", "-lc"]
    assert "news48()" in resolved
    assert sys.executable in resolved
    assert "main.py" in resolved
    assert "news48 stats --json" in resolved


def test_prepare_shell_command_normalizes_uv_run_news48():
    _, resolved = _prepare_shell_command("uv run news48 agents status --json")

    assert "uv run news48" not in resolved
    assert "news48 agents status --json" in resolved
