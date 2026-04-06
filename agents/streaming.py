"""Utilities for readable agent stream output."""

import logging
import re

logger = logging.getLogger(__name__)

_SENTENCE_BOUNDARY_RE = re.compile(r"(?:[.!?][\"')\]]*\s+|\n{2,})")

# Standard logging format:
# 2026-04-05 23:56:00 [agents._run] Executing tool: run_shell_command...
_LOG_LINE_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2})\s+"  # date
    r"(\d{2}:\d{2}):\d{2}\s+"  # time (HH:MM)
    r"\[([^\]]+)\]\s*"  # [logger name]
    r"(.+)$"  # message
)

# Message prefixes for tool execution
_PREFIX_EXEC = "Executing tool:"
_PREFIX_COMPLETE = "Completed execution of tool:"
_PREFIX_SYS_ERR = "System error while executing tool:"
_PREFIX_FAIL = "Unsuccessfully execution of the tool:"
_PREFIX_AGENT = "Agent:"


def _strip_prefix(message: str, prefix: str) -> str:
    """Remove a prefix from a message and strip whitespace."""
    return message.removeprefix(prefix).strip()


def format_log_line(line: str) -> str:
    """Parse a log line and return a human-readable format.

    Input:
        2026-04-05 23:56:00 [agents._run] Executing tool: run_shell_command...

    Output:
        23:56 ⚙ Executing: run_shell_command (Reason: ...)

    Args:
        line: A log line in standard logging format.

    Returns:
        A human-readable string, or the original line if it doesn't match.
    """
    stripped = line.strip()

    match = _LOG_LINE_RE.match(stripped)
    if not match:
        return line

    time = match.group(2)
    logger_name = match.group(3)
    message = match.group(4).strip()

    # Compact httpx lines — tool execution lines already show agent activity
    if logger_name == "httpx":
        return f"{time} 🌐 API call"

    # Parse "Agent: <content>" from AgentStream chunks
    if message.startswith(_PREFIX_AGENT):
        content = _strip_prefix(message, _PREFIX_AGENT)
        return f"{time} 💬 {content}"

    # Parse "Executing tool: <name>. Reason: <reason>"
    if message.startswith(_PREFIX_EXEC):
        rest = _strip_prefix(message, _PREFIX_EXEC)
        if ". Reason:" in rest:
            tool_name, reason = rest.split(". Reason:", 1)
            return (
                f"{time} ⚙ Executing: {tool_name.strip()} ({reason.strip()})"
            )
        return f"{time} ⚙ Executing: {rest}"

    # Parse "Completed execution of tool: <name>"
    if message.startswith(_PREFIX_COMPLETE):
        tool_name = _strip_prefix(message, _PREFIX_COMPLETE)
        return f"{time} ✔ Completed: {tool_name}"

    # Parse "System error while executing tool: <name>"
    if message.startswith(_PREFIX_SYS_ERR):
        tool_name = _strip_prefix(message, _PREFIX_SYS_ERR)
        return f"{time} ✖ Error: {tool_name}"

    # Parse "Unsuccessfully execution of the tool: <name>. Error: <error>"
    if message.startswith(_PREFIX_FAIL):
        rest = _strip_prefix(message, _PREFIX_FAIL)
        if ". Error:" in rest:
            tool_name, error = rest.split(". Error:", 1)
            return f"{time} ✖ Failed: {tool_name.strip()} ({error.strip()})"
        return f"{time} ✖ Failed: {rest}"

    # Default: just return time + message
    return f"{time} {message}"


def _emit_chunk(chunk: str) -> None:
    """Log a chunk via the logging module for file-based consumers."""
    if not chunk:
        return
    for line in chunk.strip().splitlines():
        if line.strip():
            logger.info(f"Agent: {line}")


def emit_stream_delta(stream_buffer: str, delta: str) -> tuple[str, str]:
    """Emit AgentStream deltas line-by-line as soon as newline is seen.

    This keeps live logs visible even when content has no sentence-ending
    punctuation for long stretches.

    Returns:
        tuple[remaining_buffer, emitted_text]
    """
    if not delta:
        return stream_buffer, ""

    working = stream_buffer + delta
    emitted_parts: list[str] = []

    while "\n" in working:
        line, working = working.split("\n", 1)
        if line.strip():
            emitted_parts.append(line + "\n")

    emitted_text = "".join(emitted_parts)
    if emitted_text:
        _emit_chunk(emitted_text)

    return working, emitted_text


def flush_sentence_chunks(
    stream_buffer: str, delta: str, *, max_buffer_chars: int = 2000
) -> tuple[str, str]:
    """Append delta to a stream buffer and emit readable sentence chunks.

    Returns:
        tuple[remaining_buffer, emitted_text]
    """
    if not delta:
        return stream_buffer, ""

    working = stream_buffer + delta
    emitted_parts: list[str] = []

    while True:
        match = _SENTENCE_BOUNDARY_RE.search(working)
        if not match:
            break
        end = match.end()
        piece = working[:end]
        if piece.strip():
            emitted_parts.append(piece)
        working = working[end:]

    if len(working) > max_buffer_chars:
        cutoff = working.rfind(" ")
        if cutoff <= 0:
            cutoff = max_buffer_chars
        overflow = working[:cutoff]
        if overflow.strip():
            emitted_parts.append(overflow + "\n")
        working = working[cutoff:].lstrip()

    emitted_text = "".join(emitted_parts)
    if emitted_text:
        _emit_chunk(emitted_text)

    return working, emitted_text


def flush_remaining_stream(stream_buffer: str) -> str:
    """Flush any remaining stream buffer content as a final line."""
    text = stream_buffer.strip()
    if not text:
        return ""
    final = text + "\n"
    _emit_chunk(final)
    return final
