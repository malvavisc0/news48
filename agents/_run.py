"""Shared agent run loop with standardized streaming and logging."""

import json
import logging

from llama_index.core.agent.workflow import (
    AgentStream,
    ToolCall,
    ToolCallResult,
)

from agents.streaming import emit_stream_delta, flush_remaining_stream

# Configure logging for agent execution
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


def _format_tool_kwargs(tool_name: str, kwargs: dict) -> str:
    """Format tool kwargs for logging, truncating long values."""
    if tool_name == "run_shell_command":
        cmd = kwargs.get("command", "")
        timeout = kwargs.get("timeout", "")
        truncated = cmd[:300] + ("..." if len(cmd) > 300 else "")
        return f"command={truncated!r}, timeout={timeout}"
    # Generic: truncate all values
    parts = []
    for k, v in kwargs.items():
        s = str(v)
        truncated = s[:200] + ("..." if len(s) > 200 else "")
        parts.append(f"{k}={truncated!r}")
    return ", ".join(parts)


def _summarize_tool_result(tool_name: str, output: dict) -> str:
    """Create a compact one-line summary of a tool result for logging."""
    result = output.get("result", {})

    if tool_name == "run_shell_command" and isinstance(result, dict):
        rc = result.get("return_code", "?")
        t = result.get("execution_time", "?")
        stdout = (result.get("stdout") or "")[:200]
        stderr = (result.get("stderr") or "")[:200]
        parts = [f"rc={rc}", f"time={t}s"]
        if stdout.strip():
            parts.append(f"stdout={stdout.strip()!r}")
        if stderr.strip():
            parts.append(f"stderr={stderr.strip()!r}")
        return " | ".join(parts)

    # Generic: truncate the full output
    summary = json.dumps(output, default=str)[:300]
    return summary


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
    repeated_error_count = 0
    last_tool_error_signature = ""
    repeated_error_limit = 5
    handler = get_agent_fn().run(user_msg=task, max_iterations=max_iterations)
    async for event in handler.stream_events():
        if isinstance(event, ToolCall):
            kwargs_summary = _format_tool_kwargs(
                event.tool_name, event.tool_kwargs
            )
            logger.info(
                f"Executing tool: {event.tool_name} | {kwargs_summary}"
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
                signature = f"{event.tool_name}:{error}"
                if signature == last_tool_error_signature:
                    repeated_error_count += 1
                else:
                    repeated_error_count = 1
                    last_tool_error_signature = signature

                summary = _summarize_tool_result(event.tool_name, output)
                logger.info(
                    f"Unsuccessfully execution of the tool: "
                    f"{event.tool_name} | Error: {error} | {summary}"
                )
                if repeated_error_count >= repeated_error_limit:
                    logger.info(
                        (
                            "Aborting agent loop after %d repeated "
                            "tool errors: %s"
                        ),
                        repeated_error_count,
                        signature,
                    )
                    break
                continue

            repeated_error_count = 0
            last_tool_error_signature = ""
            summary = _summarize_tool_result(event.tool_name, output)
            logger.info(
                f"Completed execution of tool: {event.tool_name} | {summary}"
            )
        elif isinstance(event, AgentStream):
            final_response += event.delta
            stream_buffer, _ = emit_stream_delta(stream_buffer, event.delta)

    flush_remaining_stream(stream_buffer)
    return final_response
