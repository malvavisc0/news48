"""Shared agent run loop with standardized streaming and logging."""

import json
import logging

from llama_index.core.agent.workflow import AgentStream, ToolCall, ToolCallResult

from agents.streaming import emit_stream_delta, flush_remaining_stream

# Configure logging for agent execution
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


def _format_tool_kwargs(tool_name: str, kwargs: dict) -> str:
    """Format tool kwargs for logging."""
    if tool_name == "run_shell_command":
        cmd = kwargs.get("command", "")
        timeout = kwargs.get("timeout", "")
        return f"command={cmd!r}, timeout={timeout}"
    # Generic: format all values
    parts = []
    for k, v in kwargs.items():
        parts.append(f"{k}={v!r}")
    return ", ".join(parts)


def _summarize_tool_result(tool_name: str, output: dict) -> str:
    """Create a compact one-line summary of a tool result for logging."""
    result = output.get("result", {})

    if tool_name == "run_shell_command" and isinstance(result, dict):
        rc = result.get("return_code", "?")
        t = result.get("execution_time", "?")
        stdout = result.get("stdout") or ""
        stderr = result.get("stderr") or ""
        parts = [f"rc={rc}", f"time={t}s"]
        if stdout.strip():
            parts.append(f"stdout={stdout.strip()!r}")
        if stderr.strip():
            parts.append(f"stderr={stderr.strip()!r}")
        return " | ".join(parts)

    # Generic: full output
    summary = json.dumps(output, default=str)
    return summary


def _is_empty_claim_result(output: dict) -> bool:
    """Check if a claim_plan result indicates no eligible plans."""
    result = output.get("result", "")
    if isinstance(result, dict):
        return result.get("status") == "no_eligible_plans"
    return result == "" or result is None


def _is_substantive_result(output: dict) -> bool:
    """Check if a tool output contains a meaningful (non-hollow) result.

    A hollow result is one where ``result`` is empty/None or is a
    ``no_eligible_plans`` sentinel.  These should NOT reset the repeated
    error counter, because the agent is not making real progress.
    """
    result = output.get("result", "")
    if not result:
        return False
    if isinstance(result, dict) and result.get("status") == "no_eligible_plans":
        return False
    return True


async def run_agent(
    get_agent_fn,
    task: str,
    max_iterations: int = 500,
) -> str:
    """Run any agent with standardized streaming and logging.

    Args:
        get_agent_fn: Callable that returns a configured FunctionAgent.
            The callable is invoked without arguments.
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
    empty_claim_count = 0
    empty_claim_limit = 2
    handler = get_agent_fn().run(user_msg=task, max_iterations=max_iterations)
    async for event in handler.stream_events():
        if isinstance(event, ToolCall):
            kwargs_summary = _format_tool_kwargs(event.tool_name, event.tool_kwargs)
            logger.info(f"Executing tool: {event.tool_name} | {kwargs_summary}")
        elif isinstance(event, ToolCallResult):
            if event.tool_output.is_error:
                logger.info(f"System error while executing tool: {event.tool_name}.")
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
                        ("Aborting agent loop after %d repeated " "tool errors: %s"),
                        repeated_error_count,
                        signature,
                    )
                    break
                continue

            # --- circuit breaker: consecutive empty claim_plan results ---
            if event.tool_name == "claim_plan" and _is_empty_claim_result(output):
                empty_claim_count += 1
                logger.info(
                    "claim_plan returned no eligible plans " "(%d/%d before abort)",
                    empty_claim_count,
                    empty_claim_limit,
                )
                if empty_claim_count >= empty_claim_limit:
                    logger.info(
                        "Aborting agent loop after %d consecutive "
                        "empty claim_plan results",
                        empty_claim_count,
                    )
                    break
            else:
                empty_claim_count = 0

            # Only reset the error counter on substantive results.
            # Hollow successes (empty result, no_eligible_plans) must NOT
            # reset the counter — otherwise alternating hollow-success /
            # error cycles prevent the repeated-error breaker from firing.
            if _is_substantive_result(output):
                repeated_error_count = 0
                last_tool_error_signature = ""

            summary = _summarize_tool_result(event.tool_name, output)
            logger.info(f"Completed execution of tool: {event.tool_name} | {summary}")
        elif isinstance(event, AgentStream):
            final_response += event.delta
            stream_buffer, _ = emit_stream_delta(stream_buffer, event.delta)

    flush_remaining_stream(stream_buffer)
    return final_response
