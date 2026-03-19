"""News parser agent module.

Provides the NewsParserAgent, a LlamaIndex FunctionAgent that extracts
structured article data from raw HTML pages.  The agent can detect and
reuse existing bash+python parser scripts or generate new ones on the fly.
"""

import json
import logging
import os
import platform
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from llama_index.core.agent import FunctionAgent
from llama_index.llms.openai_like import OpenAILike
from pydantic import BaseModel, Field

from agents.instructions import load_agent_instructions

logger = logging.getLogger(__name__)

# Default script directory for parser scripts (root level)
DEFAULT_SCRIPT_DIR = str(Path(__file__).parent.parent / "parsers")


class NewsParsingResult(BaseModel):
    title: str = Field(description="Article headline/title")
    content: str = Field(
        description=(
            "Comprehensive summary of the article containing all important "
            "information including names, references, key facts, and details"
        )
    )
    author: Optional[str] = Field(default=None, description="Author name(s)")
    published_date: Optional[str] = Field(
        default=None, description="Publication date (ISO 8601 preferred)"
    )
    url: str = Field(description="Canonical article URL")
    sentiment: Optional[str] = Field(
        default=None,
        description=(
            "Overall sentiment: 'positive', 'negative', or 'neutral'"
        ),
    )
    categories: list[str] = Field(
        default_factory=list,
        description=(
            "List of categories/topics the article belongs to "
            "(e.g., technology, politics, sports, business, entertainment)"
        ),
    )
    tags: list[str] = Field(
        default_factory=list,
        description=(
            "List of specific keywords/tags extracted from the article"
        ),
    )
    summary: Optional[str] = Field(
        default=None,
        description="Brief summary of the article (max 3 sentences)",
    )
    countries: list[str] = Field(
        default_factory=list,
        description=(
            "List of countries mentioned or involved in the article "
            "(e.g., Pakistan, Afghanistan, United States)"
        ),
    )


def _resolve_template_variables(
    command: str, script_dir: Optional[str] = None
) -> str:
    """Resolve template variables in parser commands.

    This function replaces placeholder variables in commands with their
    actual values:
    - {{PYTHON_BIN}} -> path to Python interpreter
    - {{SCRIPT_DIR}} -> directory containing parser scripts

    Args:
        command: The command string with template variables.
        script_dir: Optional custom script directory.

    Returns:
        str: Command with template variables resolved.
    """
    resolved = command

    # Resolve {{PYTHON_BIN}} - use the current Python interpreter
    python_bin = sys.executable
    resolved = resolved.replace("{{PYTHON_BIN}}", python_bin)

    # Resolve {{SCRIPT_DIR}}
    resolved_dir = script_dir or DEFAULT_SCRIPT_DIR
    resolved = resolved.replace("{{SCRIPT_DIR}}", resolved_dir)

    return resolved


def _safe_json(
    data: Dict[str, Any],
    *,
    indent: Optional[int] = 2,
    ensure_ascii: bool = True,
) -> str:
    """Safe JSON serialization with error handling.

    Args:
        data: Dictionary to serialize to JSON.
        indent: JSON indentation level. None for compact output.
        ensure_ascii: Whether to escape non-ASCII characters.

    Returns:
        str: JSON string or error message if serialization fails.
    """

    try:
        return json.dumps(
            data,
            indent=indent,
            ensure_ascii=ensure_ascii,
        )
    except (TypeError, ValueError) as exc:
        return json.dumps(
            {"error": "Serialization failed", "details": str(exc)}
        )


def _build_response(
    operation: str,
    command: str,
    working_dir: str,
    stdout: str = "",
    stderr: str = "",
    return_code: int = -1,
    execution_time: float = 0.0,
    timed_out: bool = False,
) -> Dict[str, Any]:
    """Build a standard command execution response dict.

    Args:
        operation: The operation name (e.g. "execute_command").
        command: The command that was executed.
        working_dir: The resolved working directory path.
        stdout: Captured standard output.
        stderr: Captured standard error.
        return_code: Process exit code.
        execution_time: Duration in seconds.
        timed_out: Whether the command timed out.

    Returns:
        Response dictionary with operation, result, and metadata.
    """
    return {
        "operation": operation,
        "result": {
            "stdout": stdout,
            "stderr": stderr,
            "return_code": return_code,
            "execution_time": round(execution_time, 3),
            "timed_out": timed_out,
            "command": command,
            "platform": platform.system().lower(),
            "working_dir": working_dir,
        },
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }


def run_shell_command(
    intent: str, command: str, timeout: Optional[int] = 120
) -> str:
    """Execute a shell command and return the result as JSON.

    This function runs the provided shell command using subprocess, captures
    stdout/stderr, and returns a structured JSON response with execution
    metadata including return code, timing, and any errors.

    Template variables in the command are resolved before execution:
    - {{PYTHON_BIN}} -> path to Python interpreter
    - {{SCRIPT_DIR}} -> directory containing parser scripts

    Args:
        intent: Natural-language description of what the command is intended to
                accomplish.  This parameter is consumed by the LLM for
                chain-of-thought reasoning and is intentionally unused in code.
        command: The shell command to execute. Can be any valid shell command
                 including pipes, redirects, and compound commands.
        timeout: Optional timeout in seconds for command execution.

    Returns:
        str: JSON string containing the operation result with keys:
             - operation: Always "run_shell_command"
             - result: Dict with stdout, stderr, return_code, execution_time,
                       timed_out, command, platform, working_dir
             - metadata: Dict with timestamp (ISO 8601 format)
             Returns error JSON if execution fails.
    """
    # Resolve template variables before execution
    resolved_command = _resolve_template_variables(command)

    env_vars = dict(os.environ)
    start_time = time.time()
    working_dir_str = tempfile.gettempdir()
    try:
        result = subprocess.run(
            resolved_command,
            shell=True,
            cwd=working_dir_str,
            env=env_vars,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        elapsed = time.time() - start_time

        response = _build_response(
            "run_shell_command",
            command,
            working_dir_str,
            stdout=result.stdout,
            stderr=result.stderr,
            return_code=result.returncode,
            execution_time=elapsed,
        )

        return _safe_json(response)

    except subprocess.TimeoutExpired:
        elapsed = time.time() - start_time

        return _safe_json(
            _build_response(
                "run_shell_command",
                command,
                working_dir_str,
                execution_time=elapsed,
                timed_out=True,
            )
        )
    except Exception as exc:
        return _safe_json(
            _build_response(
                "run_shell_command",
                command,
                working_dir_str,
                stderr=str(exc),
                return_code=1,
            )
        )


def read_file(intent: str, file_path: str) -> str:
    """Read a file and return its contents.

    Args:
        intent: Natural-language description of why the file is
                being read. Consumed by the LLM for reasoning.
        file_path: The path to the file to read.

    Returns:
        str: File contents (possibly summarized for HTML files),
             or an error message if reading fails.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        return f"Error: File not found: {file_path}"
    except PermissionError:
        return f"Error: Permission denied: {file_path}"
    except Exception as exc:
        return f"Error reading file {file_path}: {str(exc)}"

    return content


class NewsParserAgent(FunctionAgent):
    """Agent for parsing HTML articles from news websites.

    This agent is responsible for extracting structured article data from
    raw HTML pages. It can either reuse existing parser scripts or generate
    new ones based on the HTML structure.

    The agent uses a shell command execution tool to run parser scripts
    and expects them to output JSON-formatted article data.

    Attributes:
        name: The name of the agent (default: "NewsParser").

    Example:
        >>> from llama_index.llms.openai_like import OpenAILike
        >>> llm = OpenAILike(...)
        >>> agent = get_agent(llm)
        >>> # Agent can now parse HTML articles
    """

    @staticmethod
    def get_system_prompt() -> str:
        """Return the system prompt for the News Parser Agent.

        Returns:
            str: The complete system prompt with guidelines and best practices
                 for parsing HTML articles and generating parser scripts.
        """
        return load_agent_instructions("parser")


def get_agent(
    llm: OpenAILike,
) -> NewsParserAgent:
    """Create and configure a NewsParserAgent instance.

    This factory function creates a configured NewsParserAgent with the
    necessary tools for parsing HTML articles. The agent can detect and
    reuse existing parser scripts, or generate new ones when needed.

    Args:
        llm: The LLM instance to use for the agent's reasoning.

    Returns:
        NewsParserAgent: A configured agent instance ready for article parsing.
    """
    agent = NewsParserAgent(
        name="NewsParser",
        description=(
            "Parses HTML article pages, generates and reuses parser scripts "
            "for extracting structured article data (title, content, author, "
            "date, etc.) from news websites."
        ),
        tools=[
            run_shell_command,
            read_file,
        ],
        llm=llm,
        system_prompt=NewsParserAgent.get_system_prompt(),
        streaming=True,
        verbose=False,
        output_cls=NewsParsingResult,
    )

    return agent
