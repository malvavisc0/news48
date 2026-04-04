"""Monitor agent for intelligent system health observation."""

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

    final_response = ""
    handler = get_agent().run(user_msg=task, max_iterations=500)
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
