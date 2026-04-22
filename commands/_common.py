"""Shared utilities for CLI commands."""

import json
import sys
from datetime import datetime
from typing import NoReturn

import typer

from config import Database as DbConfig

DEFAULT_DELAY = 0.5
DATE_FMT = "%Y-%m-%d %H:%M"


def _fmt_date(iso_str: str | None) -> str:
    """Format an ISO 8601 date string for human-readable display."""
    if not iso_str:
        return "Never"
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime(DATE_FMT)
    except (ValueError, TypeError):
        return iso_str


def require_db() -> None:
    """Verify database is configured. No longer returns a path."""
    if not DbConfig.url:
        print("DATABASE_URL not configured", file=sys.stderr)
        raise typer.Exit(code=1)


def emit_json(data: dict) -> None:
    """Output data as JSON to stdout."""
    json.dump(data, sys.stdout, default=str, indent=2)
    print()


def emit_error(msg: str, as_json: bool = False) -> NoReturn:
    """Output an error message. JSON to stdout if as_json, else stderr.

    Always raises typer.Exit(code=1) after outputting.
    """
    if as_json:
        emit_json({"error": msg})
    else:
        print(f"Error: {msg}", file=sys.stderr)
    raise typer.Exit(code=1)


def status_msg(msg: str) -> None:
    """Print a status/progress message to stderr."""
    print(msg, file=sys.stderr)
