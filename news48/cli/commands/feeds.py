"""Feeds sub-app - manage feeds in the database (list, add, delete, info)."""

import sys

import typer

from news48.core.database import (
    delete_feed,
    get_articles_paginated,
    get_feed_article_count,
    get_feed_by_id,
    get_feed_by_url,
    get_feed_count,
    get_feeds_paginated,
    seed_feeds,
    update_feed_metadata,
)

from ._common import _fmt_date, emit_error, emit_json, require_db

feeds_app = typer.Typer(help="Manage feeds in the database.")


def _list_feeds(limit: int, offset: int) -> dict:
    """List all feeds in the database.

    Args:
        limit: Maximum number of feeds to display.
        offset: Number of feeds to skip.

    Returns:
        A dict with feed listing results.
    """
    require_db()

    total = get_feed_count()
    if total == 0:
        return {"total": 0, "limit": limit, "offset": offset, "feeds": []}

    feed_list = get_feeds_paginated(limit, offset)

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "feeds": [
            {
                "id": f["id"],
                "title": f["title"] or "Unknown",
                "url": f["url"],
                "last_fetched_at": f["last_fetched_at"],
            }
            for f in feed_list
        ],
    }


@feeds_app.command(name="list")
def list_feeds(
    limit: int = typer.Option(1000, "--limit", "-l", help="Number of feeds to show"),
    offset: int = typer.Option(0, "--offset", "-o", help="Number of feeds to skip"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List all feeds in the database."""
    data = _list_feeds(limit, offset)
    if output_json:
        emit_json(data)
    else:
        print(f"Feeds: {len(data['feeds'])} of {data['total']}")
        for f in data["feeds"]:
            fetched = _fmt_date(f["last_fetched_at"])
            print(f"  {f['title']} (last fetched: {fetched})")
            print(f"    {f['url']}")


def _add_feed(url: str) -> dict:
    """Add a new feed by URL.

    Args:
        url: The feed URL to add.

    Returns:
        A dict with the result.
    """
    require_db()

    if not url.startswith(("http://", "https://")):
        return {
            "added": False,
            "reason": "Invalid URL: must start with http:// or https://",
        }

    # Check if feed already exists
    existing = get_feed_by_url(url)
    if existing:
        return {
            "added": False,
            "reason": "Feed already exists",
            "id": existing["id"],
            "title": existing["title"],
        }

    # Add the feed
    count = seed_feeds([url])
    if count > 0:
        feed = get_feed_by_url(url)
        return {
            "added": True,
            "id": feed["id"] if feed else None,
            "url": url,
        }
    else:
        return {"added": False, "reason": "Failed to add feed"}


@feeds_app.command(name="add")
def add_feed(
    url: str = typer.Argument(..., help="URL of the feed to add"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Add a new feed by URL."""
    data = _add_feed(url)
    if output_json:
        emit_json(data)
    else:
        if data["added"]:
            print(f"Added feed: {data['url']} (ID: {data['id']})")
        else:
            print(f"Failed: {data['reason']}", file=sys.stderr)
            raise typer.Exit(code=1)


def _resolve_feed(identifier: str) -> tuple[dict | None, int]:
    """Look up a feed by URL or ID without deleting it.

    Args:
        identifier: The feed URL or ID to look up.

    Returns:
        A tuple of (feed dict or None, article_count).
    """
    require_db()

    feed = None
    try:
        feed_id = int(identifier)
        feed = get_feed_by_id(feed_id)
    except ValueError:
        feed = get_feed_by_url(identifier)

    if not feed:
        return None, 0

    article_count = get_feed_article_count(feed["id"])
    return feed, article_count


def _do_delete_feed(feed: dict, article_count: int) -> dict:
    """Actually delete a feed and return result dict.

    Args:
        feed: The feed dict to delete.
        article_count: Number of articles that will be removed.

    Returns:
        A dict with the deletion result.
    """
    deleted = delete_feed(feed["id"])
    if deleted:
        return {
            "deleted": True,
            "url": feed["url"],
            "articles_removed": article_count,
        }
    return {"deleted": False, "reason": "Failed to delete feed"}


@feeds_app.command(name="delete")
def delete_feed_cmd(
    identifier: str = typer.Argument(..., help="URL or ID of the feed to delete"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Delete a feed by URL or ID."""
    feed, article_count = _resolve_feed(identifier)

    if not feed:
        err = {
            "deleted": False,
            "reason": f"Feed not found: {identifier}",
        }
        if output_json:
            emit_json(err)
        else:
            print(f"Error: {err['reason']}", file=sys.stderr)
        raise typer.Exit(code=1)

    # Ask for confirmation when not forced (human mode)
    if not force and not output_json:
        confirm = typer.confirm(
            f"Delete feed '{feed['url']}'? "
            f"This will also remove {article_count} articles."
        )
        if not confirm:
            print("Deletion cancelled")
            return

    data = _do_delete_feed(feed, article_count)
    if output_json:
        emit_json(data)
    else:
        if data["deleted"]:
            print(f"Deleted feed: {data['url']}")
            if data["articles_removed"] > 0:
                print(f"Also deleted {data['articles_removed']}" " associated articles")
        else:
            print(f"Error: {data['reason']}", file=sys.stderr)
            raise typer.Exit(code=1)


def _feed_info(identifier: str) -> dict:
    """Show detailed information about a feed.

    Args:
        identifier: The feed URL or ID to show info for.

    Returns:
        A dict with feed information.
    """
    require_db()

    # Try to interpret as ID first, then as URL
    feed = None
    try:
        feed_id = int(identifier)
        feed = get_feed_by_id(feed_id)
    except ValueError:
        # Not an integer, treat as URL
        feed = get_feed_by_url(identifier)

    if not feed:
        return {"error": f"Feed not found: {identifier}"}

    # Get article count
    article_count = get_feed_article_count(feed["id"])

    return {
        "id": feed["id"],
        "url": feed["url"],
        "title": feed["title"] or "Unknown",
        "description": feed["description"],
        "last_fetched_at": feed["last_fetched_at"],
        "created_at": feed["created_at"],
        "updated_at": feed["updated_at"],
        "article_count": article_count,
    }


@feeds_app.command(name="info")
def feed_info(
    identifier: str = typer.Argument(..., help="URL or ID of the feed to show"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show detailed information about a feed."""
    try:
        data = _feed_info(identifier)
    except SystemExit:
        raise
    except Exception as e:
        emit_error(str(e), as_json=output_json)
    if "error" in data:
        emit_error(data["error"], as_json=output_json)
    if output_json:
        emit_json(data)
    else:
        print(f"ID:          {data['id']}")
        print(f"URL:         {data['url']}")
        print(f"Title:       {data['title']}")
        print(f"Description: {data['description'] or 'N/A'}")
        print(f"Last Fetched: {_fmt_date(data['last_fetched_at'])}")
        print(f"Created:     {_fmt_date(data['created_at'])}")
        print(f"Updated:     {_fmt_date(data['updated_at'])}")
        print(f"Articles:    {data['article_count']}")


@feeds_app.command(name="update")
def update_feed_cmd(
    identifier: str = typer.Argument(..., help="URL or ID of the feed to update"),
    title: str = typer.Option(None, "--title", "-t", help="New title for the feed"),
    description: str = typer.Option(
        None, "--description", "-d", help="New description for the feed"
    ),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Update feed metadata (title and/or description)."""
    require_db()

    # Validate that at least one field is specified
    if not title and not description:
        emit_error(
            "Must specify at least one of --title or --description",
            as_json=output_json,
        )

    # Try to interpret as ID first, then as URL
    feed = None
    try:
        feed_id = int(identifier)
        feed = get_feed_by_id(feed_id)
    except ValueError:
        feed = get_feed_by_url(identifier)

    if not feed:
        emit_error(
            f"Feed not found: {identifier}",
            as_json=output_json,
        )

    feed_id = feed["id"]

    # Use existing values if not provided
    new_title = title if title else feed["title"]
    new_description = description if description else feed["description"]

    # Update the feed
    update_feed_metadata(feed_id, new_title, new_description)

    # Get updated feed
    updated_feed = get_feed_by_id(feed_id)
    if not updated_feed:
        emit_error(
            "Failed to retrieve updated feed",
            as_json=output_json,
        )

    data = {
        "updated": True,
        "id": feed_id,
        "url": updated_feed["url"],
        "title": updated_feed["title"],
        "description": updated_feed["description"],
    }

    if output_json:
        emit_json(data)
    else:
        print(f"Updated feed: {data['url']}")
        print(f"  ID: {data['id']}")
        print(f"  Title: {data['title'] or 'N/A'}")
        print(f"  Description: {data['description'] or 'N/A'}")


@feeds_app.command(name="rss")
def generate_rss(
    hours: int = typer.Option(
        48, "--hours", help="Look-back window in hours for articles"
    ),
    category: str = typer.Option(None, "--category", help="Filter by category"),
    output: str = typer.Option(None, "--output", "-o", help="Output file path"),
) -> None:
    """Generate RSS feed XML for the website."""
    require_db()

    from news48.core.helpers.feed import generate_rss_feed

    articles, total = get_articles_paginated(
        limit=1000,
        hours=hours,
        category=category,
        include_source=True,
    )

    xml = generate_rss_feed(articles)

    if output:
        with open(output, "w", encoding="utf-8") as f:
            f.write(xml)
        print(f"Generated RSS feed: {output} ({total} articles)")
    else:
        print(xml)
