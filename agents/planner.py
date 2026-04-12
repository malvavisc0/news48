"""Planner agent for autonomous news48 work planning."""

from os import getenv

from llama_index.core.agent.workflow import FunctionAgent
from llama_index.llms.openai_like import OpenAILike

from agents._run import run_agent
from agents.skills import compose_agent_instructions


def get_agent(task_context: dict | None = None) -> FunctionAgent:
    """Create and return the Planner Agent.

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
        create_plan,
        get_system_info,
        list_plans,
        read_file,
        run_shell_command,
        save_lesson,
        update_plan,
    )

    ctx = task_context or {}

    return FunctionAgent(
        name="Planner",
        description=(
            "Goal-driven planning agent that gathers evidence, assesses "
            "system gaps, and creates the minimum execution plans needed "
            "for the executor to carry out."
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
            save_lesson,
        ],
        system_prompt=compose_agent_instructions("planner", ctx),
        verbose=False,
        streaming=True,
    )


async def run(task: str, task_context: dict | None = None):
    """Run the Planner Agent with a task prompt."""
    return await run_agent(lambda: get_agent(task_context), task)
