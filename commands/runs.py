"""Runs command - list recent fetch runs from the database."""

import asyncio

import typer
from rich.table import Table

from database import list_runs

from ._common import _fmt_date, console, require_db


async def _list_runs(limit: int) -> None:
    """List recent fetch runs from the database.

    Args:
        limit: Maximum number of runs to display.
    """
    db_path = require_db()

    run_list = list_runs(db_path, limit)
    if not run_list:
        console.print("[yellow]No runs found[/yellow]")
        return

    table = Table(title="Recent Runs")
    table.add_column("ID", justify="right", style="cyan")
    table.add_column("Started", style="dim")
    table.add_column("Status", style="green")
    table.add_column("Feeds", justify="right")
    table.add_column("Articles", justify="right")

    for run in run_list:
        status_style = {
            "completed": "green",
            "running": "yellow",
            "failed": "red",
        }.get(run["status"], "white")
        table.add_row(
            str(run["id"]),
            _fmt_date(run["started_at"]),
            f"[{status_style}]{run['status']}[/{status_style}]",
            str(run["feeds_fetched"]),
            str(run["articles_found"]),
        )

    console.print(table)


def runs(
    limit: int = typer.Option(
        20, "--limit", "-l", help="Number of recent runs to show"
    ),
) -> None:
    """List recent fetch runs.

    Args:
        limit: Maximum number of runs to display.
    """
    asyncio.run(_list_runs(limit))
