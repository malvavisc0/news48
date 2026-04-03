"""Fact Checker agent for selective article verification."""

import json
from os import getenv

from dotenv import load_dotenv
from llama_index.core.agent.workflow import (
    AgentStream,
    FunctionAgent,
    ToolCall,
    ToolCallResult,
)
from llama_index.llms.openai_like import OpenAILike
from loguru import logger

from agents.instructions import load_agent_instructions


def get_agent() -> FunctionAgent:
    """Create and return the Fact Checker Agent."""
    load_dotenv()

    api_base = getenv("API_BASE", "")
    if not api_base:
        raise ValueError("Missing API_BASE env.")

    from agents.tools import (
        create_plan,
        fetch_webpage_content,
        get_system_info,
        perform_web_search,
        read_file,
        run_shell_command,
        update_plan,
    )

    return FunctionAgent(
        name="Checker",
        description=(
            "Fact-checking agent that selectively verifies parsed news "
            "articles by searching for corroborating or contradicting "
            "sources, then records a verdict (verified, disputed, "
            "unverifiable, mixed) in the database."
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
            perform_web_search,
            fetch_webpage_content,
            create_plan,
            update_plan,
        ],
        system_prompt=load_agent_instructions("checker"),
        verbose=False,
        streaming=True,
    )


async def run(task: str) -> str:
    """Run the Fact Checker Agent with a task prompt.

    Args:
        task: What to do, e.g., "Fact-check 3 recently parsed articles"
              or "Verify articles about politics from the last 24 hours".

    Returns:
        The agent final response text.
    """
    agent = get_agent()
    handler = agent.run(user_msg=task, max_iterations=500)

    final_response = ""
    async for event in handler.stream_events():
        if isinstance(event, ToolCall):
            logger.info(
                f"Executing tool: {event.tool_name}. "
                f"Reason: {event.tool_kwargs.get('reason', 'Unknown')}"
            )
        elif isinstance(event, ToolCallResult):
            if event.tool_output.is_error:
                logger.info(
                    f"System error while executing tool: {event.tool_name}."
                )
                continue
            output: dict = json.loads(event.tool_output.raw_output)
            error = output.get("error", None)
            if error:
                logger.info(
                    f"Unsuccessfully execution of the tool: "
                    f"{event.tool_name}. Error: {error}."
                )
                continue
            logger.info(f"Completed execution of tool: {event.tool_name}.")
        elif isinstance(event, AgentStream):
            final_response += event.delta
            print(event.delta, end="", flush=True)

    return final_response
