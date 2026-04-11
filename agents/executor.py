"""Executor agent for autonomous news48 plan execution."""

from os import getenv

from llama_index.core.agent.workflow import FunctionAgent
from llama_index.llms.openai_like import OpenAILike

from agents._run import run_agent
from agents.skills import compose_agent_instructions


def get_agent(task_context: dict | None = None) -> FunctionAgent:
    """Create and return the Executor Agent.

    Args:
        task_context: Dict with keys like plan_family to determine which
            conditional skills to load. If None, uses empty context.
    """
    api_base = getenv("API_BASE", "")
    api_key = getenv("API_KEY", "")
    model = getenv("MODEL", "")
    if not api_base:
        raise ValueError("Missing API_BASE env.")

    from agents.tools import (
        claim_plan,
        fetch_webpage_content,
        get_system_info,
        perform_web_search,
        read_file,
        run_shell_command,
        update_plan,
    )

    ctx = task_context or {}

    return FunctionAgent(
        name="Executor",
        description=(
            "Execution agent that claims one eligible pending plan, runs its "
            "steps, performs background fetch/download/parse waves, and "
            "marks the plan completed or failed."
        ),
        llm=OpenAILike(
            model=model,
            api_base=api_base,
            api_key=api_key,
            is_chat_model=True,
            is_function_calling_model=True,
        ),
        tools=[
            claim_plan,
            update_plan,
            run_shell_command,
            read_file,
            get_system_info,
            perform_web_search,
            fetch_webpage_content,
        ],
        system_prompt=compose_agent_instructions("executor", ctx),
        verbose=False,
        streaming=True,
    )


async def run(task: str, task_context: dict | None = None):
    """Run the Executor Agent with a task prompt."""
    return await run_agent(lambda: get_agent(task_context), task)
