"""Stats command - show system statistics."""

import json

import typer
from sqlalchemy.exc import SQLAlchemyError

from news48.core.agents.tools.planner import _ensure_plans_dir
from news48.core.database import (
    check_database_health,
    get_article_stats,
    get_feed_stats,
    get_fetch_stats,
    get_retention_policy_stats,
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
    """Extract domain from a URL for display purposes."""
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


def _collect_stats(stale_days: int) -> dict:
    """Gather all stats into a single dict."""
    article = get_article_stats()
    feed = get_feed_stats(stale_days)
    fetch = get_fetch_stats()

    retention = get_retention_policy_stats()
    health = check_database_health()

    plans = {"pending": 0, "executing": 0, "completed": 0, "failed": 0}
    for plan_file in _ensure_plans_dir().glob("*.json"):
        try:
            plan = json.loads(plan_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        status = plan.get("status", "")
        if status in plans:
            plans[status] += 1

    return {
        "db_size_mb": health.get("db_size_mb", 0),
        "articles": {
            "total": _safe_int(article["total"]),
            "parsed": _safe_int(article["parsed"]),
            "unparsed": _safe_int(article["unparsed"]),
            "no_content": _safe_int(article["no_content"]),
            "download_failures": _safe_int(article["download_failed"]),
            "parse_failures": _safe_int(article["parse_failed"]),
            "download_backlog": _safe_int(article["download_backlog"]),
            "parse_backlog": _safe_int(article["parse_backlog"]),
            "malformed": _safe_int(article.get("malformed")),
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
        "retention": {
            "threshold_hours": retention["threshold_hours"],
            "articles_within_48h": retention["articles_within_48h"],
            "articles_expired": retention["articles_expired"],
            "retention_rate": retention["retention_rate"],
            "oldest_article": retention["oldest_article"],
            "newest_article": retention["newest_article"],
        },
        "health": {
            "is_connected": health["is_connected"],
            "db_size_mb": health["db_size_mb"],
            "integrity_ok": health["integrity_ok"],
            "table_counts": health["table_counts"],
        },
        "plans": plans,
    }


def _render_text(data: dict) -> None:
    """Render stats as simple text output."""
    art = data["articles"]
    sent = data["sentiment"]
    feeds = data["feeds"]
    fetches = data["fetches"]
    plans = data.get("plans", {})

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

    if art.get("malformed"):
        print(f"  Malformed (HTML in summary/title): {art['malformed']:,}")

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

    total_plans = sum(plans.values())
    if total_plans > 0:
        print(
            f"Plans: {total_plans} total, {plans['pending']} pending, "
            f"{plans['executing']} executing, {plans['completed']} completed, "
            f"{plans['failed']} failed"
        )

    # Retention Policy
    ret = data["retention"]
    print("\nRetention Policy (48-hour window):")
    print(f"  Within 48h: {ret['articles_within_48h']:,}")
    print(f"  Expired (>48h): {ret['articles_expired']:,}")
    print(f"  Retention rate: {ret['retention_rate']}%")
    if ret.get("oldest_article"):
        print(f"  Oldest article: {_fmt_date(ret['oldest_article'])}")
    if ret.get("newest_article"):
        print(f"  Newest article: {_fmt_date(ret['newest_article'])}")

    # Database Health
    hlt = data["health"]
    print("\nDatabase Health:")
    print(f"  Connected: {'✓' if hlt['is_connected'] else '✗'}")
    print(f"  Integrity: {'✓' if hlt['integrity_ok'] else '✗'}")
    if hlt.get("table_counts"):
        print("  Table counts:")
        for table, count in hlt["table_counts"].items():
            print(f"    {table}: {count:,}")


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
    """Show system statistics."""
    require_db()

    try:
        data = _collect_stats(stale_days)
    except SQLAlchemyError as exc:
        emit_error(f"Database error: {exc}", as_json=output_json)
    except Exception as exc:
        emit_error(str(exc), as_json=output_json)

    if output_json:
        emit_json(data)
    else:
        _render_text(data)
