"""Shared text processing utilities."""

import re


def strip_html_tags(text: str | None) -> str | None:
    """Remove any HTML tags from text.

    Args:
        text: Input text that may contain HTML tags.

    Returns:
        Text with all HTML tags removed, or None if input is None.
    """
    if not text:
        return text
    return re.sub(r"<[^>]+>", "", text).strip()
