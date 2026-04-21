"""Template filters and helper functions for the web interface."""

from datetime import datetime, timezone

try:
    from dateutil.parser import parse as _dateutil_parse

    def _parse_datetime(dt_str: str) -> datetime:
        """Parse a datetime string, handling ISO and RFC 2822 formats."""
        try:
            return datetime.fromisoformat(dt_str)
        except ValueError:
            return _dateutil_parse(dt_str)

except ImportError:

    def _parse_datetime(dt_str: str) -> datetime:
        """Parse a datetime string (ISO format only without dateutil)."""
        return datetime.fromisoformat(dt_str)


def format_relative_time(dt_str: str) -> str:
    """Convert ISO datetime string to relative time like '2h ago', '3d ago'."""
    if not dt_str:
        return ""
    dt = _parse_datetime(dt_str).replace(tzinfo=None)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    delta = now - dt
    total_seconds = int(delta.total_seconds())
    if total_seconds < 60:
        return "just now"
    minutes = total_seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    return f"{days}d ago"


def hours_remaining(dt_str: str) -> int:
    """Hours until 48h expiry from the given created_at timestamp."""
    if not dt_str:
        return 0
    dt = _parse_datetime(dt_str).replace(tzinfo=None)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    elapsed_hours = (now - dt).total_seconds() / 3600
    return max(0, int(48 - elapsed_hours))


def freshness_class(remaining: int) -> str:
    """Map hours remaining to a CSS freshness-bar class."""
    if remaining >= 44:
        return "f96"
    if remaining >= 40:
        return "f88"
    if remaining >= 36:
        return "f79"
    if remaining >= 28:
        return "f63"
    if remaining >= 22:
        return "f50"
    if remaining >= 14:
        return "f33"
    if remaining >= 6:
        return "f17"
    return "f8"


def freshness_bar(remaining: int) -> str:
    """Return the CSS class string for a freshness bar element."""
    return freshness_class(remaining)


def word_count(text: str) -> int:
    """Count words in text."""
    if not text:
        return 0
    return len(text.split())


def read_time(wc: int) -> int:
    """Estimate reading time in minutes from word count."""
    if wc == 0:
        return 0
    return max(1, wc // 200)


def parse_categories(categories_str: str | None) -> list[str]:
    """Split comma-separated categories into a list of stripped strings."""
    if not categories_str:
        return []
    return [c.strip() for c in categories_str.split(",") if c.strip()]


def parse_tags(tags_str: str | None) -> list[str]:
    """Split comma-separated tags into a list of stripped strings."""
    if not tags_str:
        return []
    return [t.strip() for t in tags_str.split(",") if t.strip()]


def cluster_bar(count: int, max_count: int = 10, bar_width: int = 20) -> str:
    """Generate a Unicode block bar like ██████░░░░ for cluster size.

    Args:
        count: The article count for this cluster.
        max_count: The maximum article count across all clusters (for scaling).
        bar_width: The total width of the bar in characters (default 20).
    """
    if max_count <= 0:
        max_count = 1
    ratio = count / max_count
    filled = max(1, int(ratio * bar_width)) if count > 0 else 0
    empty = bar_width - filled
    return "\u2588" * filled + "\u2591" * empty
