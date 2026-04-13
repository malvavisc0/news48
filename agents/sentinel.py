"""Sentinel agent — merged monitor + planner + feed curation."""

from os import getenv

from llama_index.core.agent.workflow import FunctionAgent
from llama_index.llms.openai_like import OpenAILike

from agents._run import run_agent
from agents.skills import compose_agent_instructions


def get_agent(task_context: dict | None = None) -> FunctionAgent:
    """Create and return the Sentinel Agent."""
    api_base = getenv("API_BASE", "")
    api_key = getenv("API_KEY", "")
    model = getenv("MODEL", "")
    if not api_base:
        raise ValueError("Missing API_BASE env.")

    from agents.tools import (
        create_plan,
        get_system_info,
        list_plans,
        read_file,
        run_shell_command,
        save_lesson,
        send_email,
        update_plan,
        write_sentinel_report,
    )

    ctx = task_context or {}

    return FunctionAgent(
        name="Sentinel",
        description=(
            "System health guardian that observes metrics, detects issues, "
            "creates fix plans, and curates feeds by removing unhealthy "
            "sources."
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
            list_plans,
            send_email,
            save_lesson,
            write_sentinel_report,
        ],
        system_prompt=compose_agent_instructions("sentinel", ctx),
        verbose=False,
        streaming=True,
    )


async def run(task: str, task_context: dict | None = None):
    """Run the Sentinel Agent with a task prompt."""
    return await run_agent(lambda: get_agent(task_context), task)
