"""Monitor agent for intelligent system health observation."""

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
    if not api_base:
        raise ValueError("Missing API_BASE env.")

    from agents.tools import get_system_info, run_shell_command

    return FunctionAgent(
        name="Monitor",
        description=(
            "Intelligent system health monitor that gathers metrics via "
            "CLI, reasons about patterns and anomalies, generates alerts "
            "with severity classification, and suggests concrete "
            "corrective actions."
        ),
        llm=OpenAILike(
            model="enfuse/smol-tools-4b-32k",
            api_base=api_base,
            is_chat_model=True,
            is_function_calling_model=True,
        ),
        tools=[
            run_shell_command,
            get_system_info,
        ],
        system_prompt=load_agent_instructions("monitor"),
        verbose=False,
        streaming=True,
    )


async def run(task: str):
    """Run the Monitor Agent with a task prompt.

    Args:
        task: What to do, e.g., "Perform a full system health check"
              or "Check for pipeline bottlenecks".
    """
    return await run_agent(get_agent, task)
