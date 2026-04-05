"""Utilities for readable agent stream output."""

import re

_SENTENCE_BOUNDARY_RE = re.compile(r"(?:[.!?][\"')\]]*\s+|\n{2,})")

# Loguru format:
# 2026-04-04 12:38:42.698 | INFO | agents.pipeline:run:77 - message
_LOGURU_LINE_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2})\s+"  # date
    r"(\d{2}:\d{2}):\d{2}\.\d+\s*\|\s*"  # time (HH:MM)
    r"\w+\s*\|\s*"  # log level
    r"[\w.]+:\w+:\d+\s*-\s*"  # module:function:line
    r"(.+)$"  # message
)

# Message prefixes for tool execution
_PREFIX_EXEC = "Executing tool:"
_PREFIX_COMPLETE = "Completed execution of tool:"
_PREFIX_SYS_ERR = "System error while executing tool:"
_PREFIX_FAIL = "Unsuccessfully execution of the tool:"


def _strip_prefix(message: str, prefix: str) -> str:
    """Remove a prefix from a message and strip whitespace."""
    return message.removeprefix(prefix).strip()


def format_log_line(line: str) -> str:
    """Parse a loguru log line and return a human-readable format.

    Input:
        2026-04-04 12:38:42.698 | INFO | agents.pipeline:run:77 -
        Executing tool: update_plan. Reason: ...

    Output:
        12:38 ⚙ Executing: update_plan (Reason: ...)

    Args:
        line: A loguru-formatted log line.

    Returns:
        A human-readable string, or the original line if it doesn't match.
    """
    match = _LOGURU_LINE_RE.match(line.strip())
    if not match:
        return line

    time = match.group(2)
    message = match.group(3).strip()

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
    """Write a chunk to stdout exactly once."""
    if not chunk:
        return
    print(chunk, end="", flush=True)


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
