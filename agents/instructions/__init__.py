import sys
from pathlib import Path


def _resolve_template_variables(content: str) -> str:
    """Resolve template variables in agent instructions.

    This function replaces placeholder variables with their actual values:
    - {{PYTHON_BIN}} -> path to Python interpreter

    Args:
        content: The content string with template variables.

    Returns:
        str: Content with template variables resolved.
    """
    # Resolve {{PYTHON_BIN}} - use the current Python interpreter
    python_bin = sys.executable
    return content.replace("{{PYTHON_BIN}}", python_bin)


def load_agent_instructions(agent_name: str) -> str:
    """Load agent instructions and resolve template variables.

    Args:
        agent_name: The name of the agent (e.g., "parser").

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
    return _resolve_template_variables(content)
