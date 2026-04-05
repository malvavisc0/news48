"""Monitor agent for system health observation and reporting."""

from os import getenv

from dotenv import load_dotenv
from llama_index.core.agent.workflow import FunctionAgent
from llama_index.llms.openai_like import OpenAILike

from agents._run import run_agent
from agents.instructions import load_agent_instructions


def get_agent() -> FunctionAgent:
    """Create and return the Monitor Agent."""
    load_dotenv()

    api_base = getenv("API_BASE", "")
    api_key = getenv("API_KEY", "")
    model = getenv("MODEL", "")
    if not api_base:
        raise ValueError("Missing API_BASE env.")

    from agents.tools import (
        get_system_info,
        read_file,
        run_shell_command,
        send_email,
    )

    return FunctionAgent(
        name="Monitor",
        description=(
            "System health observer that gathers metrics via CLI commands, "
            "reasons about patterns and anomalies, classifies alerts by "
            "severity, and delivers reports via email."
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
        ],
        system_prompt=load_agent_instructions("monitor"),
        verbose=False,
        streaming=True,
    )


async def run(task: str):
    """Run the Monitor Agent with a task prompt.

    Args:
        task: What to do, e.g., "Run a monitoring cycle and send report"
              or "Check database health and alert if critical".
    """
    return await run_agent(get_agent, task)
