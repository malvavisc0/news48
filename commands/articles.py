"""Articles sub-app - manage articles in the database (list, info)."""

import json
import os
import sys

import typer

from database import (
    claim_articles_for_processing,
    clear_article_processing_claim,
    compute_overall_verdict,
    delete_article,
    get_article_by_id,
    get_article_by_url,
    get_articles_paginated,
    get_claims_for_article,
    insert_claims,
    mark_article_parse_failed,
    reset_article_download,
    reset_article_parse,
    set_article_breaking,
    set_article_featured,
    update_article,
    update_article_fact_check,
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
        if row.get("fact_check_status"):
            return "fact-checked"
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
    language: str = typer.Option(
        None, "--language", "-L", help="Filter by language code"
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

    try:
        articles, total = get_articles_paginated(
            limit=limit,
            offset=offset,
            feed_domain=feed,
            status=status_filter,
            language=language,
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
                "processing_status": a.get("processing_status"),
                "processing_owner": a.get("processing_owner"),
                "processing_started_at": a.get("processing_started_at"),
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
    require_db()

    # Try to interpret as ID first, then as URL
    article = None
    try:
        article_id = int(identifier)
        article = get_article_by_id(article_id)
    except ValueError:
        # Not an integer, treat as URL
        article = get_article_by_url(identifier)

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

    # Try to interpret as ID first, then as URL
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

    # Ask for confirmation when not forced (human mode)
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

    # Validate that at least one flag is specified
    if not download and not parse and not all_flags:
        emit_error(
            "Must specify --download, --parse, or --all",
            as_json=output_json,
        )

    # Try to interpret as ID first, then as URL
    article = None
    try:
        article_id = int(identifier)
        article = get_article_by_id(article_id)
    except ValueError:
        article = get_article_by_url(identifier)

    if not article:
        emit_error(
            f"Article not found: {identifier}",
            as_json=output_json,
        )

    article_id = article["id"]
    reset_download = download or all_flags
    reset_parse = parse or all_flags

    # Perform resets
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

    # Try to interpret as ID first, then as URL
    article = None
    try:
        article_id = int(identifier)
        article = get_article_by_id(article_id)
    except ValueError:
        article = get_article_by_url(identifier)

    if not article:
        emit_error(
            f"Article not found: {identifier}",
            as_json=output_json,
        )

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


@articles_app.command(name="check")
def check_article(
    identifier: str = typer.Argument(..., help="Article ID or URL"),
    status: str = typer.Option(
        None,
        "--status",
        "-s",
        help="Fact-check verdict: verified|disputed|unverifiable|mixed",
    ),
    result: str = typer.Option(
        None,
        "--result",
        "-r",
        help="Free-text summary of the fact-check assessment",
    ),
    claims_json: str = typer.Option(
        None,
        "--claims-json",
        "-c",
        help="JSON array of claims: "
        '[{"claim_text", "verdict", "evidence_summary", "sources"}]',
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Overwrite existing fact-check and override active claims",
    ),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Set the fact-check status and result for an article."""
    require_db()

    # Parse claims if provided
    claims = None
    if claims_json:
        try:
            claims = json.loads(claims_json)
        except json.JSONDecodeError as e:
            emit_error(
                f"Invalid JSON for --claims-json: {e}",
                as_json=output_json,
            )

    # Validate status: required when no claims provided
    if status is None and claims is None:
        emit_error(
            "Must specify --status or --claims-json",
            as_json=output_json,
        )

    valid_statuses = {"verified", "disputed", "unverifiable", "mixed"}
    if status and status.lower() not in valid_statuses:
        emit_error(
            f"Invalid fact-check status '{status}'. "
            f"Valid: {', '.join(sorted(valid_statuses))}",
            as_json=output_json,
        )

    # Resolve article
    article = None
    try:
        article_id = int(identifier)
        article = get_article_by_id(article_id)
    except ValueError:
        article = get_article_by_url(identifier)

    if not article:
        emit_error(
            f"Article not found: {identifier}",
            as_json=output_json,
        )

    # Require article to be parsed before fact-checking
    if not article.get("parsed_at"):
        emit_error(
            f"Article {article['id']} has not been parsed yet. "
            "Parse it first before fact-checking.",
            as_json=output_json,
        )

    if article.get("fact_check_status") and not force:
        emit_error(
            f"Article {article['id']} is already fact-checked. "
            "Use --force to overwrite the existing result.",
            as_json=output_json,
        )

    claim_owner = f"fact_check:{os.getpid()}"
    claimed = claim_articles_for_processing(
        [article["id"]],
        "fact_check",
        claim_owner,
        force=force,
    )
    if article["id"] not in claimed:
        emit_error(
            f"Article {article['id']} is already being processed. "
            "Use --force to override the active claim.",
            as_json=output_json,
        )

    # Determine the final status
    if claims is not None:
        # Normalize keys: text->claim_text, evidence->evidence_summary
        normalized_claims = []
        for c in claims:
            normalized = {
                "claim_text": c.get("claim_text", c.get("text", "")),
                "verdict": c.get("verdict", "unverifiable"),
                "evidence_summary": c.get("evidence_summary", c.get("evidence", "")),
                "sources": c.get("sources", []),
            }
            normalized_claims.append(normalized)

        insert_claims(article["id"], normalized_claims)
        final_status = (
            status.lower() if status else compute_overall_verdict(normalized_claims)
        )
    else:
        final_status = status.lower()

    try:
        updated = update_article_fact_check(
            article["id"],
            status=final_status,
            result=result,
            force=force,
        )
    finally:
        clear_article_processing_claim(
            article["id"],
            owner=claim_owner,
        )

    if not updated:
        emit_error(
            f"Article {article['id']} could not be updated. "
            "It may already have a fact-check result.",
            as_json=output_json,
        )

    data = {
        "checked": updated,
        "id": article["id"],
        "url": article["url"],
        "title": article["title"],
        "fact_check_status": final_status,
        "fact_check_result": result,
        "claims_count": len(claims) if claims else 0,
    }

    if output_json:
        emit_json(data)
    else:
        title = article["title"] or "Untitled"
        if updated:
            print(f"Fact-checked article: {title}")
            print(f"  ID: {article['id']}")
            print(f"  Status: {final_status}")
            if result:
                print(f"  Result: {result}")
        else:
            print(f"Error: Failed to update article {article['id']}")


@articles_app.command(name="feature")
def feature_article(
    identifier: str = typer.Argument(..., help="Article ID or URL"),
    remove: bool = typer.Option(False, "--remove", help="Remove featured status"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Mark an article as featured."""
    require_db()

    article = None
    try:
        article_id = int(identifier)
        article = get_article_by_id(article_id)
    except ValueError:
        article = get_article_by_url(identifier)

    if not article:
        emit_error(
            f"Article not found: {identifier}",
            as_json=output_json,
        )

    featured = not remove
    set_article_featured(article["id"], featured=featured)

    data = {
        "id": article["id"],
        "url": article["url"],
        "title": article["title"],
        "is_featured": featured,
    }

    if output_json:
        emit_json(data)
    else:
        action = "Featured" if featured else "Unfeatured"
        print(f"{action} article: {article['title'] or 'Untitled'}")


@articles_app.command(name="breaking")
def breaking_article(
    identifier: str = typer.Argument(..., help="Article ID or URL"),
    remove: bool = typer.Option(False, "--remove", help="Remove breaking status"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Mark an article as breaking news."""
    require_db()

    article = None
    try:
        article_id = int(identifier)
        article = get_article_by_id(article_id)
    except ValueError:
        article = get_article_by_url(identifier)

    if not article:
        emit_error(
            f"Article not found: {identifier}",
            as_json=output_json,
        )

    breaking = not remove
    set_article_breaking(article["id"], breaking=breaking)

    data = {
        "id": article["id"],
        "url": article["url"],
        "title": article["title"],
        "is_breaking": breaking,
    }

    if output_json:
        emit_json(data)
    else:
        action = "Marked breaking" if breaking else "Unmarked breaking"
        print(f"{action}: {article['title'] or 'Untitled'}")


@articles_app.command(name="claims")
def article_claims(
    identifier: str = typer.Argument(..., help="Article ID or URL"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show per-claim fact-check results for an article."""
    require_db()

    # Resolve article
    article = None
    try:
        article_id = int(identifier)
        article = get_article_by_id(article_id)
    except ValueError:
        article = get_article_by_url(identifier)

    if not article:
        emit_error(
            f"Article not found: {identifier}",
            as_json=output_json,
        )

    claims = get_claims_for_article(article["id"])

    # Count verdicts
    verdict_counts = {}
    for c in claims:
        v = c["verdict"]
        verdict_counts[v] = verdict_counts.get(v, 0) + 1

    data = {
        "id": article["id"],
        "url": article["url"],
        "title": article["title"],
        "total_claims": len(claims),
        "verdict_counts": verdict_counts,
        "claims": claims,
    }

    if output_json:
        emit_json(data)
    else:
        title = article["title"] or "Untitled"
        print(f"Claims for: {title}")
        print(f"  ID: {article['id']}")
        print(f"  Total claims: {len(claims)}")
        if verdict_counts:
            counts = ", ".join(f"{v}: {c}" for v, c in sorted(verdict_counts.items()))
            print(f"  Verdicts: {counts}")
        print()
        for c in claims:
            print(f"  [{c['verdict']}] {c['claim_text']}")
            if c.get("evidence_summary"):
                print(f"    Evidence: {c['evidence_summary']}")
            if c.get("sources"):
                srcs = ", ".join(c["sources"])
                print(f"    Sources: {srcs}")


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
    """Update article with parsed content and metadata.

    Content MUST be provided via --content-file (no inline content).
    Sets parsed_at automatically when content-file is provided.
    """
    require_db()

    article = get_article_by_id(article_id)
    if not article:
        emit_error(f"Article not found: {article_id}", as_json=output_json)

    # Read content from file
    actual_content = None
    if content_file:
        with open(content_file, "r") as f:
            actual_content = f.read()

    # Auto-set parsed_at when content is provided
    parsed_at = None
    if actual_content:
        from datetime import datetime, timezone

        parsed_at = datetime.now(timezone.utc).isoformat()

    # Normalize published_at if provided
    normalized_published_at = None
    if published_at:
        from helpers.feed import normalize_published_date

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
