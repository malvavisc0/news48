"""Shared agent run loop with standardized streaming and logging."""

import json
import logging

from llama_index.core.agent.workflow import (
    AgentStream,
    ToolCall,
    ToolCallResult,
)

from agents.streaming import flush_remaining_stream, flush_sentence_chunks

logger = logging.getLogger(__name__)


async def run_agent(get_agent_fn, task: str, max_iterations: int = 500) -> str:
    """Run any agent with standardized streaming and logging.

    Args:
        get_agent_fn: Callable that returns a configured FunctionAgent.
        task: The task prompt to send to the agent.
        max_iterations: Maximum agent iterations (default 500).

    Returns:
        The final text response from the agent.
    """
    final_response = ""
    stream_buffer = ""
    handler = get_agent_fn().run(user_msg=task, max_iterations=max_iterations)
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
