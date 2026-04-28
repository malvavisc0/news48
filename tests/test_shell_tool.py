import sys

from news48.core.agents.tools.shell import (
    _MAIN_MODULE_PATH,
    _prepare_shell_command,
    _strip_heredocs,
    _validate_command,
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


# ---------------------------------------------------------------------------
# Heredoc stripping and blocked-pattern validation
# ---------------------------------------------------------------------------


def test_strip_heredocs_removes_content():
    """Heredoc data should be stripped before blocked-pattern checks."""
    cmd = (
        "cat > /tmp/fc-42.txt << 'CONTENT_EOF'\n"
        "The plant is in cold shutdown and has experienced 15 blackouts.\n"
        "CONTENT_EOF"
    )
    stripped = _strip_heredocs(cmd)
    assert "shutdown" not in stripped
    assert "cat > /tmp/fc-42.txt" in stripped


def test_validate_heredoc_with_shutdown_in_content():
    """Article text containing 'shutdown' inside a heredoc must not be blocked.

    Regression: the fact-checker agent writes article content to a temp
    file via ``cat > /tmp/fc-<id>.txt << 'CONTENT_EOF'``.  Articles about
    nuclear plants legitimately contain "cold shutdown", which previously
    triggered the ``\\bshutdown\\b`` blocked pattern.
    """
    cmd = (
        "cat > /tmp/fc-210.txt << 'CONTENT_EOF'\n"
        "A Ukrainian drone strike on the Zaporizhzhia nuclear power plant\n"
        "killed a transport worker. The plant, which is in cold shutdown,\n"
        "has experienced 15 blackouts since its occupation.\n"
        "CONTENT_EOF"
    )
    assert _validate_command(cmd) is None


def test_validate_heredoc_with_touch_in_content():
    """Article text containing 'touch' inside a heredoc must not be blocked."""
    cmd = (
        "cat > /tmp/fc-99.txt << 'CONTENT_EOF'\n"
        "The new policy will touch every aspect of the supply chain.\n"
        "CONTENT_EOF"
    )
    assert _validate_command(cmd) is None


def test_validate_heredoc_with_rm_in_content():
    """Article text containing 'rm' as a word inside a heredoc must not be blocked."""
    cmd = (
        "cat > /tmp/fc-50.txt << 'CONTENT_EOF'\n"
        "The firm confirmed the rm -rf report was inaccurate.\n"
        "CONTENT_EOF"
    )
    assert _validate_command(cmd) is None


def test_validate_actual_touch_command_still_blocked():
    """The ``touch`` command itself must remain blocked."""
    assert _validate_command("touch /tmp/foo") is not None


def test_validate_actual_shutdown_command_still_blocked():
    """The ``shutdown`` command itself must remain blocked."""
    assert _validate_command("shutdown -h now") is not None


def test_validate_heredoc_json_claims():
    """The fact-checker's claims JSON heredoc should pass validation."""
    cmd = (
        "cat > /tmp/fc-claims-4211.json << 'CLAIMS_EOF'\n"
        '[{"text":"Officials narrowed the draft export package.",'
        '"verdict":"verified",'
        '"evidence":"Reuters, FT, and Bloomberg independently report.",'
        '"sources":["https://reuters.com/…"]}]'
        "\nCLAIMS_EOF"
    )
    assert _validate_command(cmd) is None


def test_validate_news48_command_always_allowed():
    """news48 CLI commands should always pass validation."""
    assert _validate_command("news48 articles check 42 --json") is None
    assert _validate_command("news48 articles claims 42 --json") is None


def test_validate_blocked_pattern_outside_heredoc():
    """Blocked patterns in the actual command (not heredoc) must still be caught."""
    assert _validate_command("sudo cat /tmp/fc-42.txt") is not None
    assert _validate_command("rm -rf /tmp/fc-42.txt") is not None
