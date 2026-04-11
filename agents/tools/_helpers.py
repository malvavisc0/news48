import json
import re
from string import printable
from typing import Any, Dict, Optional


def _is_binary(sample: bytes) -> bool:
    """Determine if a byte sample contains binary data.

    A sample is considered binary if it contains a null byte (``\\x00``)
    or if more than 30% of its bytes are non-printable UTF-8 characters.

    Args:
        sample: A byte string to check (typically the first 4096 bytes
            of a file).

    Returns:
        True if the sample appears to be binary, False otherwise.
    """
    if b"\x00" in sample:
        return True

    if sample:
        printable_bytes = set(printable.encode("utf-8"))
        non_printable_ratio = sum(byte not in printable_bytes for byte in sample) / len(
            sample
        )
        if non_printable_ratio > 0.30:
            return True

    return False


def _clean_text(text: str) -> str:
    """Clean noisy text returned by search engines.

    Applies several heuristics to strip common artifacts:
    - HTML tags
    - Phonetic transcriptions  (e.g. ``/ˈiːlɒn/ EE-lon``)
    - Middle-dot (·) separated breadcrumb / navigation fragments
    - Social-media metric strings (e.g. ``237.5M Followers``)
    - Excessive whitespace

    Args:
        text: Raw text from a search result field.

    Returns:
        Cleaned text string.
    """
    if not text:
        return text

    # Strip any residual HTML tags
    text = re.sub(r"<[^>]+>", " ", text)

    # Remove phonetic transcriptions: /…/ possibly
    # followed by a pronunciation guide
    text = re.sub(r"\s*\([^)]*\)\s*", " ", text)
    text = re.sub(r"/[^/]{2,}/\s*[A-Z]+-[a-z]+;?\s*", " ", text)  # /ˈiːlɒn/ EE-lon;

    # Remove social-media metric clusters
    # e.g. "· 4.5K · 11K · 100K · 13K"
    text = re.sub(
        r"(?:[\d,.]+[KMBkmb]?\s*·\s*){2,}" r"[\d,.]+[KMBkmb]?",
        "",
        text,
    )
    # Standalone metric strings like "237.5M Followers"
    text = re.sub(
        r"\b[\d,.]+[KMBkmb]\s+"
        r"(?:Followers|Following|Views|Likes"
        r"|Posts|Reposts|Replies)\b",
        "",
        text,
        flags=re.IGNORECASE,
    )

    # Collapse middle-dot nav fragments
    # e.g. "Menü · Tesla-Aktien …" → meaningful
    # part after the last ·
    text = re.sub(r"^(?:[^·]{1,25}·\s*)+", "", text)

    # Remove IPA in square brackets e.g. [ˈiːlɒn]
    text = re.sub(r"\[[^\]]*[\u0250-\u02FF][^\]]*\]", "", text)

    # Remove "Add <Source> on Google ·" prefixes
    text = re.sub(
        r"^Add\s+.{1,50}\s+on\s+Google\s*·?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )

    # Remove relative-time prefixes: "3 days ago ·"
    text = re.sub(
        r"^\d+\s+(?:seconds?|minutes?|hours?|days?"
        r"|weeks?|months?|years?)\s+ago\s*·?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )

    # Remove "Sign up …" / "Subscribe …" trailing CTAs
    text = re.sub(
        r"\b(?:Sign up|Subscribe|Log in|Get started)\b.*$",
        "",
        text,
        flags=re.IGNORECASE,
    )

    # Remove "Read \d+ replies" fragments
    text = re.sub(
        r"\bRead\s+[\d,.]+[KMBkmb]?\s+replies\b",
        "",
        text,
        flags=re.IGNORECASE,
    )

    # Strip leftover bare middle-dot sequences
    text = re.sub(r"(?:·\s*){2,}", " ", text)

    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()

    # Strip leading/trailing middle-dots
    text = text.strip("· ").strip()

    return text


def _safe_json(
    data: Dict[str, Any],
    *,
    indent: Optional[int] = 2,
    ensure_ascii: bool = True,
) -> str:
    """Safe JSON serialization with error handling.

    Args:
        data: Dictionary to serialize to JSON.
        indent: JSON indentation level. None for compact output.
        ensure_ascii: Whether to escape non-ASCII characters.

    Returns:
        str: JSON string or error message if serialization fails.
    """

    try:
        return json.dumps(
            data,
            indent=indent,
            ensure_ascii=ensure_ascii,
        )
    except (TypeError, ValueError) as exc:
        return json.dumps({"error": "Serialization failed", "details": str(exc)})
