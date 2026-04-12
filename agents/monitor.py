"""Monitor agent for system health observation and reporting."""

from os import getenv

from llama_index.core.agent.workflow import FunctionAgent
from llama_index.llms.openai_like import OpenAILike

from agents._run import run_agent
from agents.skills import compose_agent_instructions


def get_agent(task_context: dict | None = None) -> FunctionAgent:
    """Create and return the Monitor Agent.

    Args:
        task_context: Dict with keys for conditional skill loading.
            If None, uses empty context (all core skills loaded).
    """
    api_base = getenv("API_BASE", "")
    api_key = getenv("API_KEY", "")
    model = getenv("MODEL", "")
    if not api_base:
        raise ValueError("Missing API_BASE env.")

    from agents.tools import (
        get_system_info,
        read_file,
        run_shell_command,
        save_lesson,
        send_email,
    )

    ctx = task_context or {}

    return FunctionAgent(
        name="Monitor",
        description=(
            "System health observer that gathers metrics, reasons about "
            "patterns and anomalies, classifies alerts by severity, and "
            "delivers reports via email."
        ),
        llm=OpenAILike(
            model=model,
            api_base=api_base,
            api_key=api_key,
            is_chat_model=True,
            is_function_calling_model=True,
        ),
        tools=[
            run_shell_command,
            read_file,
            get_system_info,
            send_email,
            save_lesson,
        ],
        system_prompt=compose_agent_instructions("monitor", ctx),
        verbose=False,
        streaming=True,
    )


async def run(task: str, task_context: dict | None = None):
    """Run the Monitor Agent with a task prompt.

    Args:
        task: What to do, e.g., "Run a monitoring cycle and send report"
              or "Check database health and alert if critical".
        task_context: Optional dict for conditional skill loading.
    """
    return await run_agent(lambda: get_agent(task_context), task)
