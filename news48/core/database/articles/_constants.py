"""Shared constants for article database operations."""

from datetime import datetime, timedelta, timezone

# Processing claim constants
_VALID_PROCESSING_ACTIONS = {"download", "parse", "fact_check"}
_CLAIM_TIMEOUT_MINUTES = 30

# Content quality constraints
CONTENT_MIN_CHARS = 400
CONTENT_MAX_CHARS = 10000
CONTENT_MIN_PARAGRAPHS = 2
CONTENT_MAX_PARAGRAPHS = 15
PARAGRAPH_MIN_CHARS = 100

# Summary quality constraints
SUMMARY_MIN_CHARS = 80
SUMMARY_MAX_CHARS = 420

# Title quality constraints
TITLE_MIN_CHARS = 8
TITLE_MAX_CHARS = 140

# Download-time gate
DOWNLOAD_MIN_CONTENT_CHARS = 600


def _claim_cutoff(minutes: int = _CLAIM_TIMEOUT_MINUTES) -> str:
    """Return the cutoff timestamp for stale processing claims."""
    return (
        datetime.now(timezone.utc) - timedelta(minutes=minutes)
    ).isoformat()


def _normalize_category(cat: str) -> str:
    """Normalize a category name: lowercase, replace hyphens/underscores
    with spaces, and collapse whitespace."""
    return " ".join(
        cat.strip().lower().replace("-", " ").replace("_", " ").split()
    )
