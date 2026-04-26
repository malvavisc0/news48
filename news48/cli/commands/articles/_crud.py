"""Article CRUD CLI commands: list, info, delete, reset, content, update, fail."""

import sys

import typer

from news48.core.database import (
    delete_article,
    get_article_by_id,
    get_article_by_url,
    get_articles_paginated,
    mark_article_parse_failed,
    reset_article_download,
    reset_article_parse,
    update_article,
)

from .._common import _fmt_date, emit_error, emit_json, require_db
from . import articles_app
from ._helpers import _article_status, _resolve_status


@articles_app.command(name="list")
def list_articles(
    feed: str = typer.Option(None, "--feed", help="Filter by feed domain"),
    status: str = typer.Option(
        None,
        "--status",
        "-s",
        help=(
            "Filter by status: empty, downloaded, parsed, "
            "download-failed, parse-failed, fact-checked, fact-unchecked"
        ),
    ),
    language: str = typer.Option(
        None, "--language", "-L", help="Filter by language code"
    ),
    sentiment: str = typer.Option(
        None,
        "--sentiment",
        help="Filter by sentiment: positive, negative, neutral",
    ),
    category: str = typer.Option(None, "--category", "-c", help="Filter by category"),
    country: str = typer.Option(
        None, "--country", help="Filter by country code (e.g., us, gb, de)"
    ),
    limit: int = typer.Option(20, "--limit", "-l", help="Number of articles"),
    offset: int = typer.Option(0, "--offset", "-o", help="Number to skip"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List articles with optional filters."""
    require_db()

    status_filter = None
    if status:
        status_filter = _resolve_status(status, output_json)

    if sentiment:
        valid_sentiments = {"positive", "negative", "neutral"}
        if sentiment.lower() not in valid_sentiments:
            emit_error(
                f"Invalid sentiment '{sentiment}'. "
                f"Valid: {', '.join(sorted(valid_sentiments))}",
                as_json=output_json,
            )
        sentiment = sentiment.lower()

    try:
        articles, total = get_articles_paginated(
            limit=limit,
            offset=offset,
            feed_domain=feed,
            status=status_filter,
            language=language,
            sentiment=sentiment,
            category=category,
            country=country,
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
                "sentiment": a.get("sentiment"),
                "categories": a.get("categories"),
                "processing_status": a.get("processing_status"),
                "processing_owner": a.get("processing_owner"),
                "processing_started_at": a.get("processing_started_at"),
                "created_at": a["created_at"],
            }
        )

    data = {
        "feed_filter": feed,
        "status_filter": status_filter,
        "sentiment_filter": sentiment,
        "category_filter": category,
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
        if sentiment:
            header += f" (sentiment: {sentiment})"
        if category:
            header += f" (category: {category})"
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
    require_db()

    # Try to interpret as ID first, then as URL
    article = None
    try:
        article_id = int(identifier)
        article = get_article_by_id(article_id)
    except ValueError:
        article = get_article_by_url(identifier)

    if not article:
        emit_error(f"Article not found: {identifier}", as_json=output_json)

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
    from news48.core.database import get_feed_by_id

    feed = get_feed_by_id(article["feed_id"])
    feed_url = feed["url"] if feed else None

    data = {
        "id": article["id"],
        "title": article["title"],
        "url": article["url"],
        "feed_url": feed_url,
        "content_length": (len(article["content"]) if article.get("content") else 0),
        "status": status,
        "published_at": article.get("published_at"),
        "parsed_at": article.get("parsed_at"),
        "sentiment": article.get("sentiment"),
        "categories": article.get("categories"),
        "tags": article.get("tags"),
        "countries": article.get("countries"),
        "fact_check": {
            "status": article.get("fact_check_status"),
            "result": article.get("fact_check_result"),
            "checked_at": article.get("fact_checked_at"),
        },
        "processing": {
            "status": article.get("processing_status"),
            "owner": article.get("processing_owner"),
            "started_at": article.get("processing_started_at"),
        },
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
        fc = data["fact_check"]
        if fc["status"]:
            print(f"Fact check:    {fc['status']}")
            if fc["result"]:
                print(f"  Result:      {fc['result']}")
            print(f"  Checked at:  {_fmt_date(fc['checked_at'])}")
        proc = data["processing"]
        if proc["status"]:
            print(f"Processing:    {proc['status']}")
            if proc["owner"]:
                print(f"  Owner:       {proc['owner']}")
            print(f"  Started at:  {_fmt_date(proc['started_at'])}")
        if data["errors"]["download_error"]:
            print(f"Download error: {data['errors']['download_error']}")
        if data["errors"]["parse_error"]:
            print(f"Parse error:    {data['errors']['parse_error']}")


@articles_app.command(name="delete")
def delete_article_cmd(
    identifier: str = typer.Argument(..., help="Article ID or URL to delete"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Delete an article by ID or URL."""
    require_db()

    article = None
    try:
        article_id = int(identifier)
        article = get_article_by_id(article_id)
    except ValueError:
        article = get_article_by_url(identifier)

    if not article:
        err = {"deleted": False, "reason": f"Article not found: {identifier}"}
        if output_json:
            emit_json(err)
        else:
            print(f"Error: {err['reason']}", file=sys.stderr)
        raise typer.Exit(code=1)

    article_id = article["id"]

    if not force and not output_json:
        title = article["title"] or "Untitled"
        confirm = typer.confirm(f"Delete article '{title}' (ID: {article_id})?")
        if not confirm:
            print("Deletion cancelled")
            return

    deleted = delete_article(article_id)
    data = {
        "deleted": deleted,
        "id": article_id,
        "url": article["url"],
        "title": article["title"],
    }

    if output_json:
        emit_json(data)
    else:
        if deleted:
            print(f"Deleted article: {article['title'] or 'Untitled'}")
            print(f"  ID: {article_id}")
            print(f"  URL: {article['url']}")
        else:
            print("Error: Failed to delete article", file=sys.stderr)
            raise typer.Exit(code=1)


@articles_app.command(name="reset")
def reset_article_cmd(
    identifier: str = typer.Argument(..., help="Article ID or URL to reset"),
    download: bool = typer.Option(
        False, "--download", help="Reset download failure flag"
    ),
    parse: bool = typer.Option(False, "--parse", help="Reset parse failure flag"),
    all_flags: bool = typer.Option(
        False, "--all", help="Reset both download and parse failure flags"
    ),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Reset article failure flags for retry."""
    require_db()

    if not download and not parse and not all_flags:
        emit_error(
            "Must specify --download, --parse, or --all",
            as_json=output_json,
        )

    article = None
    try:
        article_id = int(identifier)
        article = get_article_by_id(article_id)
    except ValueError:
        article = get_article_by_url(identifier)

    if not article:
        emit_error(f"Article not found: {identifier}", as_json=output_json)

    article_id = article["id"]
    reset_download = download or all_flags
    reset_parse = parse or all_flags

    if reset_download:
        reset_article_download(article_id)
    if reset_parse:
        reset_article_parse(article_id)

    data = {
        "reset": True,
        "id": article_id,
        "url": article["url"],
        "title": article["title"],
        "reset_download": reset_download,
        "reset_parse": reset_parse,
    }

    if output_json:
        emit_json(data)
    else:
        title = article["title"] or "Untitled"
        print(f"Reset article: {title}")
        print(f"  ID: {article_id}")
        flags = []
        if reset_download:
            flags.append("download")
        if reset_parse:
            flags.append("parse")
        print(f"  Reset flags: {', '.join(flags)}")


@articles_app.command(name="content")
def article_content(
    identifier: str = typer.Argument(..., help="Article ID or URL"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show article content."""
    require_db()

    article = None
    try:
        article_id = int(identifier)
        article = get_article_by_id(article_id)
    except ValueError:
        article = get_article_by_url(identifier)

    if not article:
        emit_error(f"Article not found: {identifier}", as_json=output_json)

    content = article.get("content") or ""
    data = {
        "id": article["id"],
        "title": article["title"],
        "url": article["url"],
        "content": content,
        "content_length": len(content),
    }

    if output_json:
        emit_json(data)
    else:
        title = article["title"] or "Untitled"
        print(f"Article: {title}")
        print(f"  ID: {article['id']}")
        print(f"  URL: {article['url']}")
        print(f"  Content length: {len(content):,} chars")
        print()
        if content:
            print(content)
        else:
            print("(No content)")


@articles_app.command(name="update")
def update_article_cmd(
    article_id: int = typer.Argument(..., help="Article ID to update"),
    title: str = typer.Option(None, "--title", help="Improved title"),
    content_file: str = typer.Option(
        None, "--content-file", help="File containing parsed content"
    ),
    categories: str = typer.Option(
        None, "--categories", help="Comma-separated categories"
    ),
    tags: str = typer.Option(None, "--tags", help="Comma-separated tags"),
    summary: str = typer.Option(None, "--summary", help="Article summary"),
    countries: str = typer.Option(
        None, "--countries", help="Comma-separated countries"
    ),
    sentiment: str = typer.Option(
        None, "--sentiment", help="positive|negative|neutral"
    ),
    image_url: str = typer.Option(None, "--image-url", help="Image URL"),
    language: str = typer.Option(None, "--language", help="ISO 639-1 language code"),
    published_at: str = typer.Option(None, "--published-at", help="Publication date"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Update article with parsed content and metadata."""
    require_db()

    article = get_article_by_id(article_id)
    if not article:
        emit_error(f"Article not found: {article_id}", as_json=output_json)

    actual_content = None
    if content_file:
        with open(content_file, "r") as f:
            actual_content = f.read()

    parsed_at = None
    if actual_content:
        from datetime import datetime, timezone

        parsed_at = datetime.now(timezone.utc).isoformat()

    normalized_published_at = None
    if published_at:
        from news48.core.helpers.feed import normalize_published_date

        normalized_published_at = normalize_published_date(published_at)

    update_article(
        article_id=article_id,
        content=actual_content or article.get("content", ""),
        title=title,
        categories=categories,
        tags=tags,
        summary=summary,
        countries=countries,
        sentiment=sentiment,
        image_url=image_url,
        language=language,
        published_at=normalized_published_at,
        parsed_at=parsed_at,
    )

    data = {
        "updated": True,
        "id": article_id,
        "title": title or article["title"],
        "parsed_at": parsed_at,
    }

    if output_json:
        emit_json(data)
    else:
        print(f"Updated article {article_id}: {title or article['title']}")


@articles_app.command(name="fail")
def fail_article_cmd(
    article_id: int = typer.Argument(..., help="Article ID to mark as failed"),
    error: str = typer.Option(..., "--error", "-e", help="Reason for failure"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Mark an article as parse-failed with an error message."""
    require_db()

    article = get_article_by_id(article_id)
    if not article:
        emit_error(f"Article not found: {article_id}", as_json=output_json)

    mark_article_parse_failed(article_id, error)

    data = {"failed": True, "id": article_id, "error": error}

    if output_json:
        emit_json(data)
    else:
        print(f"Marked article {article_id} as parse-failed: {error}")
