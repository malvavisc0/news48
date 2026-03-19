"""Seed command - seed the database with feed URLs from a file."""

import asyncio

import typer
from rich.progress import Progress, SpinnerColumn, TextColumn

from database import init_database, seed_feeds
from helpers import load_urls

from ._common import console, require_db


async def _seed(seed_file: str) -> None:
    """Seed the database with feed URLs from a file.

    Args:
        seed_file: Path to the seed file containing feed URLs.
    """
    db_path = require_db()

    init_database(db_path)
    urls = load_urls(seed_file)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task("Seeding feeds...", total=None)
        count = seed_feeds(db_path, urls)

    console.print(f"Seeded {count} new feeds to database")


def seed(
    seed_file: str = typer.Argument(
        ..., help="Path to the seed file containing feed URLs"
    ),
) -> None:
    """Seed the database with feed URLs from a file.

    Args:
        seed_file: Path to the seed file containing feed URLs.
    """
    asyncio.run(_seed(seed_file))
