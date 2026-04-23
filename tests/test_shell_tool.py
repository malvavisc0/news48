import sys

from news48.core.agents.tools.shell import (
    _MAIN_MODULE_PATH,
    _prepare_shell_command,
)


def test_prepare_shell_command_binds_news48_to_current_interpreter():
    argv, resolved = _prepare_shell_command("news48 stats --json")

    assert argv[:2] == ["/bin/bash", "-lc"]
    assert "news48()" in resolved
    assert sys.executable in resolved
    assert str(_MAIN_MODULE_PATH) in resolved
    assert "news48 stats --json" in resolved


def test_main_module_path_points_to_cli_main():
    """Verify _MAIN_MODULE_PATH resolves to news48/cli/main.py."""
    assert _MAIN_MODULE_PATH.name == "main.py"
    assert _MAIN_MODULE_PATH.parent.name == "cli"
    assert _MAIN_MODULE_PATH.parent.parent.name == "news48"
    assert _MAIN_MODULE_PATH.exists()


def test_prepare_shell_command_normalizes_uv_run_news48():
    _, resolved = _prepare_shell_command("uv run news48 agents status --json")

    assert "uv run news48" not in resolved
    assert "news48 agents status --json" in resolved
