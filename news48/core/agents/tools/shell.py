import os
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from ._helpers import _safe_json

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_MAIN_MODULE_PATH = _PROJECT_ROOT / "news48" / "cli" / "main.py"


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
    - Run build or deployment scripts
    - Execute git commands (clone, pull, status, etc.)
    - Search files with grep, find, or similar tools
    - Run Python scripts or other executables
    - Access command-line tools not available as functions

    ## Parameters
    - `reason` (str): Why you need to run this command
    - `command` (str): Shell command to execute (supports pipes, redirects)
    - `timeout` (int): Max seconds to wait (default: 120)

    ## Returns
    JSON with:
    - `result.working_dir`: Current directory
    - `result.stdout`: Standard output
    - `result.stderr`: Standard error
    - `result.return_code`: Exit code (0 = success)
    - `result.execution_time`: Time taken in seconds
    - `error`: Empty on success, "Operation Timeout" or exception message
    """
    env_vars = dict(os.environ)
    start_time = time.time()
    working_dir = os.getcwd()

    try:
        argv, resolved_command = _prepare_shell_command(command)
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
