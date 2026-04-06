"""Planner agent for autonomous news48 work planning."""

from os import getenv

from llama_index.core.agent.workflow import FunctionAgent
from llama_index.llms.openai_like import OpenAILike

from agents._run import run_agent
from agents.instructions import load_agent_instructions


def get_agent() -> FunctionAgent:
    """Create and return the Planner Agent."""
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
        update_plan,
    )

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
        ],
        system_prompt=load_agent_instructions("planner"),
        verbose=False,
        streaming=True,
    )


async def run(task: str):
    """Run the Planner Agent with a task prompt."""
    return await run_agent(get_agent, task)
