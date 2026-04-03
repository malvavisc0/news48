"""Articles sub-app - manage articles in the database (list, info)."""

import typer

from database import (
    get_article_by_id,
    get_article_by_url,
    get_articles_paginated,
    init_database,
)

from ._common import _fmt_date, emit_error, emit_json, require_db

articles_app = typer.Typer(help="Manage articles in the database.")


def _resolve_status(status: str, as_json: bool = False) -> str:
    """Validate and normalize a status filter value.

    Args:
        status: The status string from the CLI.
        as_json: Whether to output errors as JSON.

    Returns:
        The normalized status string.
    """
    valid = {
        "empty",
        "downloaded",
        "parsed",
        "download-failed",
        "parse-failed",
    }
    if status not in valid:
        emit_error(
            f"Invalid status '{status}'. "
            f"Valid: {', '.join(sorted(valid))}",
            as_json=as_json,
        )
    return status


def _article_status(row: dict) -> str:
    """Derive the status string from an article row.

    Args:
        row: An article dict from get_articles_paginated.

    Returns:
        The status string.
    """
    if row.get("download_failed"):
        return "download-failed"
    if row.get("parse_failed"):
        return "parse-failed"
    if row.get("is_parsed"):
        return "parsed"
    if row.get("has_content"):
        return "downloaded"
    return "empty"


@articles_app.command(name="list")
def list_articles(
    feed: str = typer.Option(None, "--feed", help="Filter by feed domain"),
    status: str = typer.Option(
        None,
        "--status",
        "-s",
        help="Filter: empty|downloaded|parsed|download-failed|parse-failed",
    ),
    limit: int = typer.Option(20, "--limit", "-l", help="Number of articles"),
    offset: int = typer.Option(0, "--offset", "-o", help="Number to skip"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List articles with optional filters."""
    db_path = require_db()
    init_database(db_path)

    status_filter = None
    if status:
        status_filter = _resolve_status(status, output_json)

    try:
        articles, total = get_articles_paginated(
            db_path,
            limit=limit,
            offset=offset,
            feed_domain=feed,
            status=status_filter,
        )
    except SystemExit:
        raise
    except Exception as e:
        emit_error(str(e), as_json=output_json)

    # Build output
    article_list = []
    for a in articles:
        article_list.append(
            {
                "id": a["id"],
                "title": a["title"],
                "url": a["url"],
                "feed_url": a["feed_url"],
                "status": _article_status(a),
                "created_at": a["created_at"],
            }
        )

    data = {
        "feed_filter": feed,
        "status_filter": status_filter,
        "total": total,
        "limit": limit,
        "offset": offset,
        "articles": article_list,
    }

    if output_json:
        emit_json(data)
    else:
        header = f"Articles: {len(article_list)} of {total}"
        if feed:
            header += f" (feed: {feed})"
        if status_filter:
            header += f" (status: {status_filter})"
        print(header)
        for a in article_list:
            title = a["title"] or "Untitled"
            print(f"  [{a['status']}] {title}")
            print(f"    {a['url']}")


@articles_app.command(name="info")
def article_info(
    identifier: str = typer.Argument(..., help="Article ID or URL"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show article metadata (no content -- use temp files for content)."""
    db_path = require_db()
    init_database(db_path)

    # Try to interpret as ID first, then as URL
    article = None
    try:
        article_id = int(identifier)
        article = get_article_by_id(db_path, article_id)
    except ValueError:
        # Not an integer, treat as URL
        article = get_article_by_url(db_path, identifier)

    if not article:
        emit_error(
            f"Article not found: {identifier}",
            as_json=output_json,
        )

    # Derive status
    if article.get("download_failed"):
        status = "download-failed"
    elif article.get("parse_failed"):
        status = "parse-failed"
    elif article.get("parsed_at"):
        status = "parsed"
    elif article.get("content"):
        status = "downloaded"
    else:
        status = "empty"

    # Get feed URL
    from database import get_feed_by_id

    feed = get_feed_by_id(db_path, article["feed_id"])
    feed_url = feed["url"] if feed else None

    data = {
        "id": article["id"],
        "title": article["title"],
        "url": article["url"],
        "feed_url": feed_url,
        "content_length": (
            len(article["content"]) if article.get("content") else 0
        ),
        "status": status,
        "published_at": article.get("published_at"),
        "parsed_at": article.get("parsed_at"),
        "sentiment": article.get("sentiment"),
        "categories": article.get("categories"),
        "tags": article.get("tags"),
        "countries": article.get("countries"),
        "errors": {
            "download_error": article.get("download_error"),
            "parse_error": article.get("parse_error"),
        },
    }

    if output_json:
        emit_json(data)
    else:
        print(f"ID:            {data['id']}")
        print(f"Title:         {data['title'] or 'Untitled'}")
        print(f"URL:           {data['url']}")
        print(f"Feed URL:      {data['feed_url']}")
        print(f"Status:        {data['status']}")
        print(f"Content length: {data['content_length']:,} chars")
        print(f"Published:     {_fmt_date(data['published_at'])}")
        print(f"Parsed:        {_fmt_date(data['parsed_at'])}")
        if data["sentiment"]:
            print(f"Sentiment:     {data['sentiment']}")
        if data["categories"]:
            print(f"Categories:    {data['categories']}")
        if data["tags"]:
            print(f"Tags:          {data['tags']}")
        if data["countries"]:
            print(f"Countries:     {data['countries']}")
        if data["errors"]["download_error"]:
            print(f"Download error: {data['errors']['download_error']}")
        if data["errors"]["parse_error"]:
            print(f"Parse error:    {data['errors']['parse_error']}")
