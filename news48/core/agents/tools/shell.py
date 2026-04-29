import logging
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from ._helpers import _safe_json

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_MAIN_MODULE_PATH = _PROJECT_ROOT / "news48" / "cli" / "main.py"

# ---------------------------------------------------------------------------
# Command allowlist — only these base commands may be executed.
# The ``news48`` command is special-cased: it is rewritten to use the
# current Python interpreter via _prepare_shell_command().
#
# SECURITY: Commands that allow arbitrary code execution (python, pip),
# credential leakage (env, printenv), network activity (git push/clone),
# service disruption (alembic downgrade, dramatiq, uvicorn), or filesystem
# modification (cp, mv, mkdir, touch) are blocked via _BLOCKED_PATTERNS.
#
# Shell operators (|, ;, &, >, <, <<) are intentionally ALLOWED because
# the agents use them for:
#   - Heredocs:    cat > /tmp/fc-claims.json << 'EOF' ... EOF
#   - Parallel:    news48 download ... > /tmp/out.log 2>&1 &
#   - Wave sync:   wait $PID; EXIT=$?
#   - Pipes:       cat /tmp/out.log
#   - Downloads:   curl -o /tmp/file.json https://example.com/data
# The _BLOCKED_PATTERNS regex catches dangerous commands (python,
# etc.) even when they appear after a pipe or in a subshell.
# ---------------------------------------------------------------------------
_ALLOWED_BASE_COMMANDS = frozenset(
    {
        "news48",
        # Network download tools — used to fetch external resources into /tmp
        "curl",
        "wget",
        # Scripting interpreters
        "python",
        "python3",
        # Read-only inspection + agent workflow commands
        "ls",
        "cat",
        "head",
        "tail",
        "wc",
        "grep",
        "find",
        "sort",
        "uniq",
        "echo",
        "date",
        "pwd",
        "du",
        "df",
        "file",
        "stat",
        # Shell builtins used in wave execution patterns
        "wait",
        "sleep",
        "if",
        "then",
        "fi",
        "test",
    }
)

# Patterns that are always blocked regardless of allowlist.
# These are checked against the full command string, so they catch
# dangerous programs even when invoked after a pipe or in a subshell.
_BLOCKED_PATTERNS = re.compile(
    r"(?:"
    r"\bnc\b|\bncat\b|\bnmap\b"  # network exfil
    r"|\bssh\b|\bscp\b|\brsync\b"  # remote access
    r"|\bchmod\b|\bchown\b|\bchgrp\b"  # permission changes
    r"|\bkill\b|\bpkill\b|\bshutdown\b|\breboot\b"  # process/system control
    r"|\bmount\b|\bumount\b"  # filesystem mounts
    r"|\bsudo\b|\bsu\b"  # privilege escalation
    r"|\beval\b|\bexec\b"  # code execution
    r"|\bdd\b"  # raw disk access
    r"|\bcrontab\b"  # scheduled tasks
    r"|\biptables\b|\bufw\b"  # firewall
    r"|\bbase64\b.*-d"  # encoded payloads
    r"|/dev/tcp\b|/dev/udp\b"  # bash network
    r"|\bmkfifo\b|\bmknod\b"  # named pipes
    r"|\bperl\b|\bruby\b|\bnode\b"  # interpreters (python allowed)
    r"|\bpip[0-9]*\b"  # package installers
    r"|\benv\b|\bprintenv\b"  # env var leakage
    r"|\bgit\b"  # network-capable VCS
    r"|\balembic\b|\bdramatiq\b|\buvicorn\b"  # service management
    r"|\bmkdir\b|\bcp\b|\bmv\b|\btouch\b|\brm\b"  # filesystem mutation
    r")",
    re.IGNORECASE,
)


def _strip_heredocs(command: str) -> str:
    """Remove heredoc content from a command before validation.

    Heredocs (``<< 'EOF' ... EOF``) may contain arbitrary article text
    that legitimately includes words matching blocked patterns (e.g.
    "shutdown" in "cold shutdown").  We strip the data portion so only
    the actual command tokens are validated.
    """
    # Match << or <<-, optional quoted delimiter, then everything until
    # the delimiter appears on its own line.
    return re.sub(
        r"<<-?\s*['\"]?(\w+)['\"]?\b.*?\n.*?^\1\s*$",
        "",
        command,
        flags=re.DOTALL | re.MULTILINE,
    )


def _validate_command(command: str) -> str | None:
    """Validate that a shell command is allowed.

    Returns None if the command is valid, or an error message if blocked.
    """
    stripped = command.strip()
    if not stripped:
        return "Empty command"

    # Check for blocked patterns in the command portion only,
    # stripping heredoc data to avoid false positives from article text.
    checkable = _strip_heredocs(stripped)
    blocked_match = _BLOCKED_PATTERNS.search(checkable)
    if blocked_match:
        return (
            f"Command contains blocked pattern: '{blocked_match.group()}'. "
            "Only safe read-only and news48 pipeline commands are allowed."
        )

    # Extract the first token (base command) after normalizing news48 prefix
    normalized = stripped.replace("uv run news48", "news48")
    first_token = normalized.split()[0] if normalized.split() else ""

    # Handle absolute/relative paths — extract basename
    base_cmd = os.path.basename(first_token)

    # Allow news48 subcommands unconditionally
    if base_cmd == "news48" or first_token == "news48":
        return None

    # Check against allowlist
    if base_cmd not in _ALLOWED_BASE_COMMANDS:
        return (
            f"Command '{base_cmd}' is not in the allowlist. "
            f"Allowed: {', '.join(sorted(_ALLOWED_BASE_COMMANDS))}"
        )

    return None


def _prepare_shell_command(command: str) -> tuple[list[str], str]:
    """Prepare a shell command with a bound ``news48`` function.

    The function ensures that any ``news48`` invocation uses the same Python
    interpreter that is currently running the agent tool.

    Args:
        command: The raw shell command requested by the agent.

    Returns:
        A tuple of (argv, resolved_command_string).
    """
    python_bin = shlex.quote(sys.executable)
    main_path = shlex.quote(str(_MAIN_MODULE_PATH))

    normalized = command.replace("uv run news48", "news48")
    resolved_command = (
        "news48() { " f'{python_bin} {main_path} "$@"; ' "}\n" f"{normalized}"
    )
    return ["/bin/bash", "-lc", resolved_command], resolved_command


def run_shell_command(reason: str, command: str, timeout: Optional[int] = 120) -> str:
    """Execute a shell command and return its output.

    ## When to Use
    Use this tool when you need to run system commands for file operations,
    git operations, running scripts, or any task that requires shell access.
    Prefer using specific file tools when available.

    ## Why to Use
    - Run news48 CLI commands (fetch, parse, download, etc.)
    - Search files with grep, find, or similar tools
    - Check file listings and system state
    - Run git commands (status, log, diff)

    ## Parameters
    - `reason` (str): Why you need to run this command
    - `command` (str): Shell command to execute (must be in allowlist)
    - `timeout` (int): Max seconds to wait (default: 120)

    ## Returns
    JSON with:
    - `result.working_dir`: Current directory
    - `result.stdout`: Standard output
    - `result.stderr`: Standard error
    - `result.return_code`: Exit code (0 = success)
    - `result.execution_time`: Time taken in seconds
    - `error`: Empty on success, "Operation Timeout" or error message

    ## Security
    Only commands in the allowlist are permitted. Blocked patterns include
    privilege escalation (sudo), destructive operations (rm -rf, chmod),
    interpreters (perl, ruby, node), and credential leakage (env, printenv).
    curl, wget, python, and python3 are allowed.
    """
    # Validate command before execution
    validation_error = _validate_command(command)
    if validation_error:
        logger.warning("Blocked shell command: %s — %s", command, validation_error)
        return _safe_json({"result": "", "error": validation_error})

    env_vars = dict(os.environ)
    start_time = time.time()
    working_dir = os.getcwd()

    try:
        argv, resolved_command = _prepare_shell_command(command)
        logger.info(
            "Executing shell command: reason=%s command=%s",
            reason,
            command,
        )
        result = subprocess.run(
            argv,
            cwd=working_dir,
            env=env_vars,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        response = {
            "working_dir": working_dir,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "return_code": result.returncode,
            "execution_time": time.time() - start_time,
            "resolved_command": resolved_command,
            "python_executable": sys.executable,
        }
        return _safe_json({"result": response, "error": ""})
    except subprocess.TimeoutExpired:
        return _safe_json({"result": "", "error": "Operation Timeout"})
    except Exception as exc:
        return _safe_json({"result": "", "error": str(exc)})
