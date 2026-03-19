import sys
from pathlib import Path

# Default script directory for parser scripts (root level)
DEFAULT_SCRIPT_DIR = str(Path(__file__).parent.parent / "parsers")


def _resolve_template_variables(
    content: str,
    script_dir: str | None = None,
) -> str:
    """Resolve template variables in agent instructions.

    This function replaces placeholder variables with their actual values:
    - {{PYTHON_BIN}} -> path to Python interpreter
    - {{SCRIPT_DIR}} -> directory containing parser scripts

    Args:
        content: The content string with template variables.
        script_dir: Optional custom script directory.

    Returns:
        str: Content with template variables resolved.
    """
    resolved = content

    # Resolve {{PYTHON_BIN}} - use the current Python interpreter
    python_bin = sys.executable
    resolved = resolved.replace("{{PYTHON_BIN}}", python_bin)

    # Resolve {{SCRIPT_DIR}}
    resolved_dir = script_dir or DEFAULT_SCRIPT_DIR
    resolved = resolved.replace("{{SCRIPT_DIR}}", resolved_dir)

    return resolved


def load_agent_instructions(
    agent_name: str,
    script_dir: str | None = None,
) -> str:
    """Load agent instructions and resolve template variables.

    Args:
        agent_name: The name of the agent (e.g., "parser").
        script_dir: Optional custom script directory. Defaults to parsers/.

    Returns:
        str: The instructions content with template variables resolved.
    """
    instructions_dir = Path(__file__).parent
    parts = []

    instructions_path = instructions_dir / f"{agent_name}.md"
    if instructions_path.exists():
        with open(instructions_path, mode="r", encoding="utf-8") as file:
            parts.append(file.read())

    content = "\n\n".join(parts)

    # Resolve template variables before returning
    return _resolve_template_variables(content, script_dir)
