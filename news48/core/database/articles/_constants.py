"""Shared constants for article database operations."""

from datetime import datetime, timedelta, timezone

from news48.core.helpers.security import escape_like

# Processing claim constants
_VALID_PROCESSING_ACTIONS = {"download", "parse", "fact_check"}
_CLAIM_TIMEOUT_MINUTES = 30


def _claim_cutoff(minutes: int = _CLAIM_TIMEOUT_MINUTES) -> str:
    """Return the cutoff timestamp for stale processing claims."""
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()


def _normalize_category(cat: str) -> str:
    """Normalize a category name: lowercase, replace hyphens/underscores
    with spaces, and collapse whitespace."""
    return " ".join(cat.strip().lower().replace("-", " ").replace("_", " ").split())
