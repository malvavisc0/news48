"""Shared text processing utilities."""

import re
from html import unescape


def strip_html_tags(text: str | None) -> str | None:
    """Remove HTML tags and decode HTML entities from text.

    Args:
        text: Input text that may contain HTML tags or entities.

    Returns:
        Text with tags removed and entities decoded, or None.
    """
    if not text:
        return text
    return unescape(re.sub(r"<[^>]+>", "", text)).strip()
