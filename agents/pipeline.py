"""Pipeline agent for autonomous news48 pipeline execution."""

from os import getenv

from dotenv import load_dotenv
from llama_index.core.agent.workflow import FunctionAgent
from llama_index.llms.openai_like import OpenAILike

from agents._run import run_agent
from agents.instructions import load_agent_instructions


def get_agent() -> FunctionAgent:
    """Create and return the Pipeline Agent."""
    load_dotenv()

    api_base = getenv("API_BASE", "")
    api_key = getenv("API_KEY", "")
    model = getenv("MODEL", "")
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
        name="Pipeline",
        description=(
            "Autonomous pipeline agent that runs the news48 pipeline: "
            "fetch feeds, download articles, parse content, and purge "
            "expired. Runs stages one at a time, inspects results between "
            "stages, handles failures with retries, and enforces retention "
            "policy."
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
            create_plan,
            update_plan,
        ],
        system_prompt=load_agent_instructions("pipeline"),
        verbose=False,
        streaming=True,
    )


async def run(task: str):
    """Run the Pipeline Agent with a task prompt.

    Args:
        task: What to do, e.g., "Run a full pipeline cycle" or
              "Fetch and download articles from arstechnica.com"
    """
    return await run_agent(get_agent, task)
