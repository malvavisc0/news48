"""Shared utilities for CLI commands."""

from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console

from config import Database as DbConfig

DEFAULT_DELAY = 0.5
DATE_FMT = "%Y-%m-%d %H:%M"

console = Console(width=120)


def _fmt_date(iso_str: str | None) -> str:
    """Format an ISO 8601 date string for human-readable display."""
    if not iso_str:
        return "Never"
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime(DATE_FMT)
    except (ValueError, TypeError):
        return iso_str


def require_db() -> Path:
    """Return the DB path or exit with an error."""
    if not DbConfig.path:
        console.print("[red]DATABASE_PATH not configured[/red]")
        raise typer.Exit(code=1)
    return DbConfig.path
