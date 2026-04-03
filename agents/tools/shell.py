import os
import subprocess
import time
from datetime import datetime, timezone
from typing import Optional

from agents.tools._helpers import _get_function_name, _safe_json


def run_shell_command(
    reason: str, command: str, timeout: Optional[int] = 120
) -> str:
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
    timestamp = datetime.now(timezone.utc).isoformat()
    env_vars = dict(os.environ)
    start_time = time.time()
    working_dir = os.getcwd()

    try:
        result = subprocess.run(
            command,
            shell=True,
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
        }
        return _safe_json(
            {
                "result": response,
                "error": "",
                "metadata": {
                    "timestamp": timestamp,
                    "reason": reason,
                    "params": {"command": command, "timeout": timeout},
                    "success": True,
                },
                "operation": _get_function_name(),
            }
        )
    except subprocess.TimeoutExpired:
        return _safe_json(
            {
                "result": "",
                "error": "Operation Timeout",
                "metadata": {
                    "timestamp": timestamp,
                    "reason": reason,
                    "params": {"command": command, "timeout": timeout},
                    "success": False,
                },
                "operation": _get_function_name(),
            }
        )
    except Exception as exc:
        return _safe_json(
            {
                "result": "",
                "error": str(exc),
                "metadata": {
                    "timestamp": timestamp,
                    "reason": reason,
                    "params": {"command": command, "timeout": timeout},
                    "success": False,
                },
                "operation": _get_function_name(),
            }
        )
