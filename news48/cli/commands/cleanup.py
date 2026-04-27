"""Cleanup command - enforce 48-hour data retention policy."""

import re

import typer

from news48.core.database import (
    check_database_health,
    get_articles_older_than_hours,
    get_retention_policy_stats,
    purge_articles_older_than_hours,
)
from news48.core.database.connection import SessionLocal

from ._common import emit_error, emit_json, require_db

# Patterns to strip from summaries (same as text.py _TRUNCATION_RE)
_TRUNCATION_PATTERNS = [
    r"\s*\[?\.{2,}\]?\s*",
    r"\s*\[…\]\s*",
    r"\s*\(more\)\s*",
    r"\s*\(continued\)\s*",
    r"\s*Continue reading\s*$",
    r"\s*Read more\s*$",
    r"\s*Read full article\s*$",
    r"\s*Read the full story\s*$",
]
_TRUNCATION_RE = re.compile("|".join(_TRUNCATION_PATTERNS), re.IGNORECASE)

cleanup_app = typer.Typer(
    help=(
        "Manage data retention and cleanup.\n\n"
        "news48 enforces a 48-hour retention window by default.\n"
        "Articles older than this are candidates for purging."
    ),
)


@cleanup_app.command(name="status")
def cleanup_status(
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show 48-hour retention policy status."""
    require_db()

    try:
        stats = get_retention_policy_stats()
    except Exception as e:
        emit_error(str(e), as_json=output_json)

    if output_json:
        emit_json(stats)
    else:
        print("Retention Policy Status (48-hour window)")
        print(f"  Total articles: {stats['total_articles']:,}")
        print(f"  Within 48h: {stats['articles_within_48h']:,}")
        print(f"  Expired (>48h): {stats['articles_expired']:,}")
        print(f"  Retention rate: {stats['retention_rate']}%")
        print(f"  Oldest article: {stats['oldest_article'] or 'N/A'}")
        print(f"  Newest article: {stats['newest_article'] or 'N/A'}")


@cleanup_app.command(name="purge")
def cleanup_purge(
    hours: int = typer.Option(48, "--hours", "-h", help="Hours threshold"),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        "-n",
        help="Show what would be deleted without deleting",
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Skip confirmation"
    ),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Purge articles older than the retention threshold.

    The default retention window is 48 hours. Use --dry-run to
    preview what would be deleted without actually removing data.

    Examples:
        news48 cleanup purge
        news48 cleanup purge --dry-run
        news48 cleanup purge --hours 72 --force --json
    """
    require_db()

    # Get articles that would be purged
    try:
        old_articles = get_articles_older_than_hours(hours)
    except Exception as e:
        emit_error(str(e), as_json=output_json)

    if not old_articles:
        if output_json:
            emit_json(
                {
                    "purged": 0,
                    "threshold_hours": hours,
                    "dry_run": dry_run,
                    "message": "No articles found older than threshold",
                }
            )
        else:
            print(f"No articles found older than {hours} hours")
        return

    # Show preview
    if not output_json and not dry_run:
        print(f"Found {len(old_articles)} articles older than {hours} hours:")
        for article in old_articles[:10]:
            title = article.get("title") or "Untitled"
            print(f"  - [{article['id']}] {title}")
            print(f"    Created: {article['created_at']}")
        if len(old_articles) > 10:
            print(f"  ... and {len(old_articles) - 10} more")
        print()

    # Confirm deletion
    if not force and not dry_run and not output_json:
        confirm = typer.confirm(
            f"Purge {len(old_articles)} articles older than {hours} hours?"
        )
        if not confirm:
            print("Purge cancelled")
            return

    # Execute purge
    try:
        result = purge_articles_older_than_hours(hours, dry_run)
    except Exception as e:
        emit_error(str(e), as_json=output_json)

    if output_json:
        emit_json(result)
    else:
        if dry_run:
            print(f"[DRY RUN] Would purge {result['articles_found']} articles")
        else:
            deleted = result["articles_deleted"]
            print(f"Purged {deleted} articles older than {hours} hours")


@cleanup_app.command(name="health")
def cleanup_health(
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Check database health and connectivity."""
    require_db()

    try:
        health = check_database_health()
    except Exception as e:
        emit_error(str(e), as_json=output_json)

    if output_json:
        emit_json(health)
    else:
        print("Database Health Check")
        print(f"  Connected: {'✓' if health['is_connected'] else '✗'}")
        print(f"  Size: {health['db_size_mb']} MB")
        print(f"  Integrity: {'✓' if health['integrity_ok'] else '✗'}")
        print("  Table counts:")
        for table, count in health["table_counts"].items():
            print(f"    {table}: {count:,}")


@cleanup_app.command(name="summaries")
def cleanup_summaries(
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        "-n",
        help="Show what would be cleaned without updating",
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Skip confirmation"
    ),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Clean truncation markers from article summaries.

    Removes patterns like 'Continue reading', '[...]', '(more)', etc.
    from the end of summaries. Use --dry-run to preview changes.

    Examples:
        news48 cleanup summaries
        news48 cleanup summaries --dry-run
        news48 cleanup summaries --force --json
    """
    require_db()

    from sqlalchemy import text

    # Find articles with truncation markers
    with SessionLocal() as session:
        rows = session.execute(
            text(
                """
                SELECT id, summary FROM articles
                WHERE summary IS NOT NULL
                AND (
                    summary LIKE '%Continue reading%'
                    OR summary LIKE '%continue reading%'
                    OR summary LIKE '%Read more%'
                    OR summary LIKE '%read more%'
                    OR summary LIKE '%Read full article%'
                    OR summary LIKE '%Read the full story%'
                    OR summary LIKE '%[...]%'
                    OR summary LIKE '%(more)%'
                    OR summary LIKE '%(continued)%'
                )
            """
            )
        ).fetchall()

        articles = [dict(row._mapping) for row in rows]

    if not articles:
        if output_json:
            emit_json({"cleaned": 0, "message": "No summaries need cleaning"})
        else:
            print("No summaries need cleaning")
        return

    # Show preview
    if not output_json and not dry_run:
        print(f"Found {len(articles)} articles with truncation markers:")
        for article in articles[:5]:
            summary = article.get("summary") or ""
            # Show last 100 chars
            preview = summary[-100:] if len(summary) > 100 else summary
            print(f"  - [{article['id']}] ...{preview}")
        if len(articles) > 5:
            print(f"  ... and {len(articles) - 5} more")
        print()

    # Confirm
    if not force and not dry_run and not output_json:
        confirm = typer.confirm(f"Clean {len(articles)} article summaries?")
        if not confirm:
            print("Cleanup cancelled")
            return

    # Execute cleanup
    cleaned = 0
    for article in articles:
        original = article["summary"]
        cleaned_summary = _TRUNCATION_RE.sub("", original).strip()
        if cleaned_summary != original:
            if not dry_run:
                from sqlalchemy import text as sql_text

                with SessionLocal() as session:
                    session.execute(
                        sql_text(
                            "UPDATE articles SET summary = :summary"
                            " WHERE id = :id"
                        ),
                        {"summary": cleaned_summary, "id": article["id"]},
                    )
                    session.commit()
            cleaned += 1

    if output_json:
        emit_json(
            {
                "total_found": len(articles),
                "cleaned": cleaned,
                "dry_run": dry_run,
            }
        )
    else:
        if dry_run:
            print(f"[DRY RUN] Would clean {cleaned} summaries")
        else:
            print(f"Cleaned {cleaned} article summaries")


# Markdown patterns that indicate LLM-generated formatting.
_MD_PATTERNS_RE = re.compile(
    r"\*\*[^*]+\*\*"  # **bold**
    r"|__[^_]+__"  # __bold__
    r"|(?<!\*)\*(?!\*)[^*]+\*(?!\*)"  # *italic* (not **)
    r"|^#{1,6}\s+"  # # heading at line start
    r"|^\s{0,3}>\s?"  # > blockquote at line start
    r"|^\s{0,3}[-*+]\s+"  # - list item at line start
    r"|^\s{0,3}\d+\.\s+"  # 1. ordered list at line start
    r"|^\s{0,3}---\s*$"  # --- horizontal rule
    r"|\[[^\]]+\]\([^)]+\)"  # [text](url) links
    r"|`[^`]+`"  # `inline code`
    r"|~~[^~]+~~",  # ~~strikethrough~~
    re.MULTILINE,
)


@cleanup_app.command(name="markdown")
def cleanup_markdown(
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        "-n",
        help="Show what would be cleaned without updating",
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Skip confirmation"
    ),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Strip markdown formatting from article content, titles, and summaries.

    Removes bold, italic, headings, links, blockquotes, list markers,
    horizontal rules, code, and strikethrough from all parsed articles.
    Use --dry-run to preview changes.

    Examples:
        news48 cleanup markdown
        news48 cleanup markdown --dry-run
        news48 cleanup markdown --force --json
    """
    require_db()

    from sqlalchemy import text as sql_text

    from news48.core.helpers.text import strip_markdown

    # Find parsed articles that contain markdown patterns.
    with SessionLocal() as session:
        rows = session.execute(
            sql_text(
                """
                SELECT id, title, summary, content FROM articles
                WHERE parsed_at IS NOT NULL
                AND (
                    content LIKE '%**%'
                    OR title LIKE '%**%'
                    OR summary LIKE '%**%'
                    OR content LIKE '%## %'
                    OR title LIKE '%## %'
                    OR content LIKE '%](http%'
                    OR content LIKE '%`%'
                )
            """
            )
        ).fetchall()

        articles = [dict(row._mapping) for row in rows]

    if not articles:
        if output_json:
            emit_json(
                {"cleaned": 0, "message": "No articles with markdown found"}
            )
        else:
            print("No articles with markdown formatting found")
        return

    # Filter to only articles where stripping actually changes something.
    needs_cleaning = []
    for article in articles:
        changes = {}
        for field in ("title", "summary", "content"):
            original = article.get(field) or ""
            cleaned = strip_markdown(original)
            if cleaned != original:
                changes[field] = cleaned
        if changes:
            needs_cleaning.append({"id": article["id"], "changes": changes})

    if not needs_cleaning:
        if output_json:
            emit_json(
                {"cleaned": 0, "message": "No articles need markdown removal"}
            )
        else:
            print("No articles need markdown removal")
        return

    # Show preview
    if not output_json and not dry_run:
        print(
            f"Found {len(needs_cleaning)} articles with markdown formatting:"
        )
        for item in needs_cleaning[:5]:
            fields = ", ".join(item["changes"].keys())
            print(f"  - [{item['id']}] fields: {fields}")
        if len(needs_cleaning) > 5:
            print(f"  ... and {len(needs_cleaning) - 5} more")
        print()

    # Confirm
    if not force and not dry_run and not output_json:
        confirm = typer.confirm(
            f"Strip markdown from {len(needs_cleaning)} articles?"
        )
        if not confirm:
            print("Cleanup cancelled")
            return

    # Execute cleanup
    cleaned = 0
    for item in needs_cleaning:
        if not dry_run:
            sets = []
            params = {"id": item["id"]}
            for field, value in item["changes"].items():
                sets.append(f"{field} = :{field}")
                params[field] = value
            set_clause = ", ".join(sets)
            with SessionLocal() as session:
                session.execute(
                    sql_text(
                        f"UPDATE articles SET {set_clause}" " WHERE id = :id"
                    ),
                    params,
                )
                session.commit()
        cleaned += 1

    if output_json:
        emit_json(
            {
                "total_found": len(needs_cleaning),
                "cleaned": cleaned,
                "dry_run": dry_run,
            }
        )
    else:
        if dry_run:
            print(f"[DRY RUN] Would strip markdown from {cleaned} articles")
        else:
            print(f"Stripped markdown from {cleaned} articles")
