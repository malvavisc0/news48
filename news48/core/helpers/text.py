"""Shared text processing utilities."""

import re
from html import unescape

# Common RSS truncation markers to strip after entity decoding.
_TRUNCATION_RE = re.compile(
    r"\s*\[?\.{2,}\]?\s*|\s*\[…\]\s*|\s*\(more\)\s*|\s*\(continued\)\s*",
    re.IGNORECASE,
)


def strip_html_tags(text: str | None) -> str | None:
    """Remove HTML tags, decode entities, and strip truncation markers.

    Args:
        text: Input text that may contain HTML tags or entities.

    Returns:
        Cleaned text, or None if input is None.
    """
    if not text:
        return text
    cleaned = unescape(re.sub(r"<[^>]+>", "", text)).strip()
    cleaned = _TRUNCATION_RE.sub("", cleaned).strip()
    return cleaned
