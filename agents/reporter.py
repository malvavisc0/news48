"""Reporter agent for natural language report generation."""

from os import getenv

from dotenv import load_dotenv
from llama_index.core.agent.workflow import FunctionAgent
from llama_index.llms.openai_like import OpenAILike

from agents._run import run_agent
from agents.instructions import load_agent_instructions


def get_agent() -> FunctionAgent:
    """Create and return the Reporter Agent."""
    load_dotenv()

    api_base = getenv("API_BASE", "")
    if not api_base:
        raise ValueError("Missing API_BASE env.")

    from agents.tools import (
        create_plan,
        get_system_info,
        read_file,
        run_shell_command,
        update_plan,
    )

    return FunctionAgent(
        name="Reporter",
        description=(
            "Natural language report generator that gathers pipeline "
            "data, analyzes performance trends, tracks retention "
            "compliance, and writes executive-style summaries with "
            "concrete metrics."
        ),
        llm=OpenAILike(
            model="enfuse/smol-tools-4b-32k",
            api_base=api_base,
            is_chat_model=True,
            is_function_calling_model=True,
        ),
        tools=[
            run_shell_command,
            read_file,
            get_system_info,
            create_plan,
            update_plan,
        ],
        system_prompt=load_agent_instructions("reporter"),
        verbose=False,
        streaming=True,
    )


async def run(task: str):
    """Run the Reporter Agent with a task prompt.

    Args:
        task: What to do, e.g., "Generate a daily pipeline report"
              or "Write a weekly summary of system activity".
    """
    return await run_agent(get_agent, task)
