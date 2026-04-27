"""Shared text processing utilities."""

import re
from html import unescape

# Common RSS truncation markers to strip after entity decoding.
_TRUNCATION_RE = re.compile(
    r"\s*\[?\.{2,}\]?\s*|\s*\[…\]\s*|\s*\(more\)\s*|\s*\(continued\)\s*"
    r"|\s*Continue reading\s*$"
    r"|\s*Read more\s*$"
    r"|\s*Read full article\s*$"
    r"|\s*Read the full story\s*$",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Markdown stripping — removes common markdown syntax from LLM output.
# ---------------------------------------------------------------------------

# Order matters: block-level patterns first, then inline patterns.

# Heading prefixes: # , ## , ### , etc. at line start.
_MD_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+", re.MULTILINE)

# Horizontal rules: ---, ***, ___ on their own line.
_MD_HRULE_RE = re.compile(r"^\s{0,3}([-*_])\s*\1\s*\1[\s\1]*$", re.MULTILINE)

# Blockquote prefixes: > at line start (including nested >>, >>>, etc.).
_MD_BLOCKQUOTE_RE = re.compile(r"^\s{0,3}>+\s?", re.MULTILINE)

# Unordered list markers: - , * , + at line start (but not inside words).
# Uses a negative lookbehind to avoid matching mid-word asterisks.
_MD_ULIST_RE = re.compile(r"^\s{0,3}[-*+]\s+", re.MULTILINE)

# Ordered list markers: 1. , 2. , etc. at line start.
_MD_OLIST_RE = re.compile(r"^\s{0,3}\d+\.\s+", re.MULTILINE)

# Fenced code blocks: ``` or ~~~ with optional language tag.
_MD_FENCED_RE = re.compile(
    r"^\s{0,3}(?:`{3,}|~{3,}).*?$.*?^\s{0,3}(?:`{3,}|~{3,})\s*$",
    re.MULTILINE | re.DOTALL,
)

# Inline code: `code` (single backtick pairs).
_MD_INLINE_CODE_RE = re.compile(r"`([^`]+)`")

# Images: ![alt](url) → alt text (strip before links to avoid partial match).
_MD_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")

# Links: [text](url) → text.
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")

# Bold+italic: ***text*** or ___text___ → text.
_MD_BOLDITALIC_RE = re.compile(r"(\*{3}|_{3})(.+?)\1")

# Bold: **text** or __text__ → text.
_MD_BOLD_RE = re.compile(r"(\*{2}|_{2})(.+?)\1")

# Italic: *text* or _text_ → text.
# Uses word-boundary-aware pattern to avoid matching mid-word underscores.
_MD_ITALIC_STAR_RE = re.compile(r"\*([^\s*](?:[^*]*[^\s*])?)\*")
_MD_ITALIC_UNDER_RE = re.compile(
    r"(?<![a-zA-Z0-9])_([^\s_](?:[^_]*[^\s_])?)_(?![a-zA-Z0-9])"
)

# Strikethrough: ~~text~~ → text.
_MD_STRIKETHROUGH_RE = re.compile(r"~~(.+?)~~")

# HTML tags that markdown renderers emit (already handled by strip_html_tags,
# but included here for standalone use).
_MD_HTML_RE = re.compile(r"<[^>]+>")


def strip_markdown(text: str | None) -> str | None:
    """Remove markdown formatting from text, returning plain text.

    Strips headings, bold, italic, links, images, code blocks, blockquotes,
    list markers, horizontal rules, and strikethrough.  Intended as a
    defense-in-depth layer after ``strip_html_tags``.

    Args:
        text: Input text that may contain markdown syntax.

    Returns:
        Cleaned plain text, or None if input is None.
    """
    if not text:
        return text

    s = text

    # 1. Block-level: fenced code blocks (replace entire block with content)
    s = _MD_FENCED_RE.sub(lambda m: _fenced_inner(m), s)

    # 2. Block-level: headings, hrules, blockquotes, list markers
    s = _MD_HEADING_RE.sub("", s)
    s = _MD_HRULE_RE.sub("", s)
    s = _MD_BLOCKQUOTE_RE.sub("", s)
    s = _MD_ULIST_RE.sub("", s)
    s = _MD_OLIST_RE.sub("", s)

    # 3. Inline: images → alt text, links → text
    s = _MD_IMAGE_RE.sub(r"\1", s)
    s = _MD_LINK_RE.sub(r"\1", s)

    # 4. Inline: bold+italic, bold, italic, strikethrough
    s = _MD_BOLDITALIC_RE.sub(r"\2", s)
    s = _MD_BOLD_RE.sub(r"\2", s)
    s = _MD_INLINE_CODE_RE.sub(r"\1", s)
    s = _MD_ITALIC_STAR_RE.sub(r"\1", s)
    s = _MD_ITALIC_UNDER_RE.sub(r"\1", s)
    s = _MD_STRIKETHROUGH_RE.sub(r"\1", s)

    # 5. Collapse multiple blank lines into at most two newlines.
    s = re.sub(r"\n{3,}", "\n\n", s)

    return s.strip()


def _fenced_inner(match: re.Match) -> str:
    """Extract inner content of a fenced code block, stripping fences."""
    lines = match.group(0).split("\n")
    # Drop first line (opening fence) and last line (closing fence).
    inner = "\n".join(lines[1:-1])
    return inner


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
