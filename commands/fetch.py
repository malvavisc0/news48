"""Fetch command - fetch and parse RSS/Atom feeds from URLs stored."""

import asyncio

import typer
from rich.table import Table

from database import get_all_feeds, init_database
from helpers import get_fetch_summary

from ._common import DEFAULT_DELAY, console, require_db


async def _fetch(delay: float) -> None:
    """Async entry point: load URLs from database, fetch feeds.

    Args:
        delay: Delay between requests in seconds.
    """
    db_path = require_db()
    init_database(db_path)

    feeds = get_all_feeds(db_path)
    if not feeds:
        console.print(
            "[yellow]No feeds found in database. Run 'seed' first.[/yellow]"
        )
        return

    urls = [feed["url"] for feed in feeds]
    summary = await get_fetch_summary(urls, delay, db_path)

    table = Table(title="Feed Summary")
    table.add_column("Feed Title", style="cyan")
    table.add_column("Entries", justify="right", style="green")
    table.add_column("Valid", justify="right", style="yellow")
    table.add_column("URL", style="dim")

    for result in summary.successful:
        table.add_row(
            result.title or "Unknown",
            str(result.entry_count),
            str(result.valid_articles_count),
            result.url,
        )

    console.print(table)
    console.print(
        f"Total: {len(summary.successful)} feeds, "
        f"{sum(r.entry_count for r in summary.successful)} entries, "
        f"{sum(r.valid_articles_count for r in summary.successful)} valid"
    )
    console.print(f"Success rate: {summary.success_rate:.1f}%")

    if summary.failed:
        failed_table = Table(title="Failed Feeds", style="red")
        failed_table.add_column("URL", style="cyan")
        failed_table.add_column("Error", style="red")

        for result in summary.failed:
            failed_table.add_row(result.url, result.error or "Unknown error")

        console.print(failed_table)
        console.print(f"Total failed: {len(summary.failed)}")


def fetch(
    delay: float = typer.Option(
        DEFAULT_DELAY,
        "--delay",
        "-d",
        help="Delay between requests in seconds",
    ),
) -> None:
    """Fetch and parse RSS/Atom feeds from URLs stored in the database.

    Feeds must be seeded first using the 'seed' command. Results are
    automatically saved to the database.

    Args:
        delay: Delay between requests in seconds.
    """
    asyncio.run(_fetch(delay))
