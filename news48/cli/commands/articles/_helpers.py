"""Shared helpers for article CLI commands."""

from .._common import emit_error


def _resolve_status(status: str, as_json: bool = False) -> str:
    """Validate and normalize a status filter value."""
    valid = {
        "empty",
        "downloaded",
        "parsed",
        "download-failed",
        "parse-failed",
        "fact-checked",
        "fact-unchecked",
    }
    if status not in valid:
        emit_error(
            f"Invalid status '{status}'. " f"Valid: {', '.join(sorted(valid))}",
            as_json=as_json,
        )
    return status


def _article_status(row: dict) -> str:
    """Derive the status string from an article row."""
    if row.get("download_failed"):
        return "download-failed"
    if row.get("parse_failed"):
        return "parse-failed"
    if row.get("is_parsed"):
        if row.get("fact_check_status"):
            return "fact-checked"
        return "parsed"
    if row.get("has_content"):
        return "downloaded"
    return "empty"
