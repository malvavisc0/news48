"""Feeds sub-app - manage feeds in the database (list, add, delete, info)."""

import asyncio

import typer
from rich.table import Table

from database import (
    delete_feed,
    get_feed_article_count,
    get_feed_by_id,
    get_feed_by_url,
    get_feed_count,
    get_feeds_paginated,
    init_database,
    seed_feeds,
)

from ._common import _fmt_date, console, require_db

feeds_app = typer.Typer(help="Manage feeds in the database.")


async def _list_feeds(limit: int, offset: int) -> None:
    """List all feeds in the database.

    Args:
        limit: Maximum number of feeds to display.
        offset: Number of feeds to skip.
    """
    db_path = require_db()

    init_database(db_path)

    total = get_feed_count(db_path)
    if total == 0:
        console.print("[yellow]No feeds found in database[/yellow]")
        return

    feed_list = get_feeds_paginated(db_path, limit, offset)

    table = Table(title=f"Feeds (showing {len(feed_list)} of {total})")
    table.add_column("ID", justify="right", style="cyan")
    table.add_column("Title", style="green")
    table.add_column("URL", style="dim")
    table.add_column("Last Fetched", style="yellow")

    for feed in feed_list:
        table.add_row(
            str(feed["id"]),
            feed["title"] or "Unknown",
            feed["url"],
            _fmt_date(feed["last_fetched_at"]),
        )

    console.print(table)


@feeds_app.command(name="list")
def list_feeds(
    limit: int = typer.Option(
        20, "--limit", "-l", help="Number of feeds to show"
    ),
    offset: int = typer.Option(
        0, "--offset", "-o", help="Number of feeds to skip"
    ),
) -> None:
    """List all feeds in the database."""
    asyncio.run(_list_feeds(limit, offset))


async def _add_feed(url: str) -> None:
    """Add a new feed by URL.

    Args:
        url: The feed URL to add.
    """
    db_path = require_db()

    if not url.startswith(("http://", "https://")):
        console.print(f"[red]Invalid URL: {url}[/red]")
        console.print("URL must start with http:// or https://")
        raise typer.Exit(code=1)

    init_database(db_path)

    # Check if feed already exists
    existing = get_feed_by_url(db_path, url)
    if existing:
        console.print(f"[yellow]Feed already exists: {url}[/yellow]")
        console.print(f"  ID: {existing['id']}")
        console.print(f"  Title: {existing['title'] or 'Unknown'}")
        raise typer.Exit(code=1)

    # Add the feed
    count = seed_feeds(db_path, [url])
    if count > 0:
        # Get the newly created feed to show its ID
        feed = get_feed_by_url(db_path, url)
        console.print(f"[green]Added feed: {url}[/green]")
        if feed:
            console.print(f"  ID: {feed['id']}")
    else:
        console.print(f"[red]Failed to add feed: {url}[/red]")
        raise typer.Exit(code=1)


@feeds_app.command(name="add")
def add_feed(
    url: str = typer.Argument(..., help="URL of the feed to add")
) -> None:
    """Add a new feed by URL."""
    asyncio.run(_add_feed(url))


async def _delete_feed(identifier: str, force: bool) -> None:
    """Delete a feed by URL or ID.

    Args:
        identifier: The feed URL or ID to delete.
        force: Skip confirmation prompt.
    """
    db_path = require_db()

    init_database(db_path)

    # Try to interpret as ID first, then as URL
    feed = None
    try:
        feed_id = int(identifier)
        feed = get_feed_by_id(db_path, feed_id)
    except ValueError:
        # Not an integer, treat as URL
        feed = get_feed_by_url(db_path, identifier)

    if not feed:
        console.print(f"[red]Feed not found: {identifier}[/red]")
        raise typer.Exit(code=1)

    # Get article count before deletion
    article_count = get_feed_article_count(db_path, feed["id"])

    # Confirm deletion
    if not force:
        console.print(f"Delete feed: {feed['url']}")
        console.print(f"  ID: {feed['id']}")
        console.print(f"  Title: {feed['title'] or 'Unknown'}")
        console.print(f"  Articles: {article_count}")
        confirm = typer.confirm("Are you sure you want to delete this feed?")
        if not confirm:
            console.print("[yellow]Deletion cancelled[/yellow]")
            return

    # Delete the feed (also deletes associated articles)
    deleted = delete_feed(db_path, feed["id"])
    if deleted:
        console.print(f"[green]Deleted feed: {feed['url']}[/green]")
        if article_count > 0:
            msg = f"Also deleted {article_count} associated articles"
            console.print(f"[green]{msg}[/green]")
    else:
        console.print("[red]Failed to delete feed[/red]")
        raise typer.Exit(code=1)


@feeds_app.command(name="delete")
def delete_feed_cmd(
    identifier: str = typer.Argument(
        ..., help="URL or ID of the feed to delete"
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Skip confirmation prompt"
    ),
) -> None:
    """Delete a feed by URL or ID."""
    asyncio.run(_delete_feed(identifier, force))


async def _feed_info(identifier: str) -> None:
    """Show detailed information about a feed.

    Args:
        identifier: The feed URL or ID to show info for.
    """
    db_path = require_db()

    init_database(db_path)

    # Try to interpret as ID first, then as URL
    feed = None
    try:
        feed_id = int(identifier)
        feed = get_feed_by_id(db_path, feed_id)
    except ValueError:
        # Not an integer, treat as URL
        feed = get_feed_by_url(db_path, identifier)

    if not feed:
        console.print(f"[red]Feed not found: {identifier}[/red]")
        raise typer.Exit(code=1)

    # Get article count
    article_count = get_feed_article_count(db_path, feed["id"])

    # Display feed info
    console.print("\n[bold cyan]Feed Information[/bold cyan]")
    console.print(f"ID:          {feed['id']}")
    console.print(f"URL:         {feed['url']}")
    console.print(f"Title:       {feed['title'] or 'Unknown'}")
    console.print(f"Description: {feed['description'] or 'N/A'}")
    console.print(f"Last Fetched: {_fmt_date(feed['last_fetched_at'])}")
    console.print(f"Created:     {_fmt_date(feed['created_at'])}")
    console.print(f"Updated:     {_fmt_date(feed['updated_at'])}")
    console.print(f"Articles:    {article_count}")


@feeds_app.command(name="info")
def feed_info(
    identifier: str = typer.Argument(
        ..., help="URL or ID of the feed to show"
    ),
) -> None:
    """Show detailed information about a feed."""
    asyncio.run(_feed_info(identifier))
