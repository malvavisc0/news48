"""Reporter agent for natural language report generation."""

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
from agents.streaming import flush_remaining_stream, flush_sentence_chunks


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

    final_response = ""
    stream_buffer = ""
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
            stream_buffer, _ = flush_sentence_chunks(
                stream_buffer, event.delta
            )

    flush_remaining_stream(stream_buffer)

    return final_response
