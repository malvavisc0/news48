"""Shared stats collector for CLI and web surfaces."""

from news48.core.agents.tools.planner._db import db_iter_plans

from . import (
    check_database_health,
    get_article_stats,
    get_feed_stats,
    get_fetch_stats,
    get_retention_policy_stats,
)


def _safe_int(value: int | float | str | None) -> int:
    """Coerce a value to int, defaulting to 0 for None."""
    if value is None:
        return 0
    return int(value)


def collect_stats(stale_days: int = 7) -> dict:
    """Gather all monitor/CLI stats into a single dict."""
    article = get_article_stats()
    feed = get_feed_stats(stale_days)
    fetch = get_fetch_stats()
    retention = get_retention_policy_stats()
    health = check_database_health()

    plans = {"pending": 0, "executing": 0, "completed": 0, "failed": 0}
    for plan in db_iter_plans():
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
