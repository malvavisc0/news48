"""Stats command - show system statistics."""

import os
import sqlite3
from pathlib import Path

import typer

from database import (
    get_article_stats,
    get_feed_stats,
    get_fetch_stats,
    init_database,
)

from ._common import _fmt_date, emit_error, emit_json, require_db


def _format_size(size_bytes: int) -> str:
    """Format a byte count as a human-readable size string."""
    if size_bytes > 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    if size_bytes > 1024:
        return f"{size_bytes / 1024:.2f} KB"
    return f"{size_bytes} bytes"


def _extract_domain(url: str) -> str:
    """Extract domain from a URL for display purposes.

    Args:
        url: A URL string.

    Returns:
        The domain portion of the URL, or the original URL if parsing fails.
    """
    try:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        return parsed.netloc or url
    except Exception:
        return url


def _safe_int(value: int | float | str | None) -> int:
    """Coerce a value to int, defaulting to 0 for None."""
    if value is None:
        return 0
    return int(value)


def _collect_stats(db_path: Path, stale_days: int) -> dict:
    """Gather all stats into a single dict.

    Args:
        db_path: Path to the SQLite database file.
        stale_days: Days before a feed is considered stale.

    Returns:
        A dict containing database, articles, feeds, and runs stats.
    """
    db_size = os.path.getsize(db_path)

    article = get_article_stats(db_path)
    feed = get_feed_stats(db_path, stale_days)
    fetch = get_fetch_stats(db_path)

    return {
        "db_size_mb": round(db_size / (1024 * 1024), 2),
        "articles": {
            "total": _safe_int(article["total"]),
            "parsed": _safe_int(article["parsed"]),
            "unparsed": _safe_int(article["unparsed"]),
            "no_content": _safe_int(article["no_content"]),
            "download_failures": _safe_int(article["download_failed"]),
            "parse_failures": _safe_int(article["parse_failed"]),
            "download_backlog": _safe_int(article["download_backlog"]),
            "parse_backlog": _safe_int(article["parse_backlog"]),
            "articles_today": _safe_int(article["articles_today"]),
            "articles_this_week": _safe_int(article["articles_this_week"]),
            "oldest_unparsed_at": article.get("oldest_unparsed_at"),
        },
        "sentiment": {
            "positive": _safe_int(article["sentiment_positive"]),
            "negative": _safe_int(article["sentiment_negative"]),
            "neutral": _safe_int(article["sentiment_neutral"]),
        },
        "feeds": {
            "total": _safe_int(feed["total"]),
            "never_fetched": _safe_int(feed["never_fetched"]),
            "stale": _safe_int(feed["stale"]),
            "stale_days": stale_days,
            "top_feeds": feed.get("top_feeds", []),
        },
        "fetches": {
            "total": _safe_int(fetch["total_runs"]),
            "last_fetch_at": fetch.get("last_run_at"),
            "avg_articles_per_fetch": fetch.get("avg_articles_per_run"),
            "recent": fetch.get("recent_runs", []),
        },
    }


def _render_text(data: dict) -> None:
    """Render stats as simple text output.

    Args:
        data: The stats dict from _collect_stats.
    """
    art = data["articles"]
    sent = data["sentiment"]
    feeds = data["feeds"]
    fetches = data["fetches"]

    # Database
    print(f"Database: {data['db_size_mb']} MB")

    # Articles
    print(
        f"Articles: {art['total']:,} total, {art['parsed']:,} parsed, "
        f"{art['unparsed']:,} unparsed, {art['no_content']:,} no content"
    )
    if art["download_failures"]:
        print(f"  Download failures: {art['download_failures']:,}")
    if art["parse_failures"]:
        print(f"  Parse failures: {art['parse_failures']:,}")
    print(
        f"  New today: {art['articles_today']:,}, "
        f"this week: {art['articles_this_week']:,}"
    )

    # Pipeline Health
    print(
        f"Pipeline: download backlog {art['download_backlog']:,}, "
        f"parse backlog {art['parse_backlog']:,}"
    )
    oldest = art.get("oldest_unparsed_at")
    if oldest:
        print(f"  Oldest unparsed: {_fmt_date(oldest)}")

    # Sentiment
    total_sent = sent["positive"] + sent["negative"] + sent["neutral"]
    if total_sent > 0:
        print(
            f"Sentiment: positive {sent['positive']:,}, "
            f"negative {sent['negative']:,}, neutral {sent['neutral']:,}"
        )

    # Feeds
    print(
        f"Feeds: {feeds['total']:,} total, "
        f"{feeds['never_fetched']:,} never fetched, "
        f"{feeds['stale']:,} stale (>{feeds['stale_days']}d)"
    )

    top = feeds.get("top_feeds", [])
    if top:
        print("Top feeds:")
        for i, f in enumerate(top, 1):
            title = f.get("title")
            if not title:
                title = _extract_domain(f.get("url", "Unknown"))
            count = _safe_int(f.get("article_count"))
            print(f"  {i}. {title} ({count} articles)")

    # Fetches
    print(f"Fetches: {fetches['total']:,} total")
    avg = fetches.get("avg_articles_per_fetch")
    if avg is not None:
        print(f"  Avg articles/fetch: {avg}")
    recent = fetches.get("recent", [])
    if recent:
        print("Recent fetches:")
        for r in recent:
            status = r.get("status", "unknown")
            icon = {"completed": "+", "failed": "x"}.get(status, "~")
            print(
                f"  [{icon}] #{r.get('id', '?')} "
                f"{_fmt_date(r.get('started_at'))} - {status} "
                f"({r.get('feeds_fetched', 0)} feeds, "
                f"{r.get('articles_found', 0)} articles)"
            )


def stats(
    output_json: bool = typer.Option(
        False,
        "--json",
        help="Output stats as JSON for scripting",
    ),
    stale_days: int = typer.Option(
        7,
        "--stale-days",
        help="Days before a feed is considered stale",
    ),
) -> None:
    """Show system statistics.

    Displays database size, article counts, pipeline health,
    sentiment distribution, feed statistics, and recent run
    history.
    """
    db_path = require_db()
    init_database(db_path)

    try:
        data = _collect_stats(db_path, stale_days)
    except sqlite3.DatabaseError as exc:
        emit_error(f"Database error: {exc}", as_json=output_json)
    except Exception as exc:
        emit_error(str(exc), as_json=output_json)

    if output_json:
        emit_json(data)
    else:
        _render_text(data)
