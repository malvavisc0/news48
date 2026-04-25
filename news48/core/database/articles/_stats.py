"""Article and feed statistics aggregation queries."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from ..connection import SessionLocal, _hours_ago_iso
from ._browsing import get_topic_clusters


def get_article_stats() -> dict:
    """Get consolidated article statistics in a single query."""
    with SessionLocal() as session:
        row = session.execute(text("""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN parsed_at IS NOT NULL THEN 1 ELSE 0 END)
                    AS parsed,
                SUM(CASE WHEN parsed_at IS NULL THEN 1 ELSE 0 END)
                    AS unparsed,
                SUM(CASE WHEN content IS NULL OR content = ''
                    THEN 1 ELSE 0 END) AS no_content,
                SUM(CASE WHEN download_failed = 1 THEN 1 ELSE 0 END)
                    AS download_failed,
                SUM(CASE WHEN parse_failed = 1 THEN 1 ELSE 0 END)
                    AS parse_failed,
                SUM(CASE WHEN content IS NULL AND download_failed = 0
                    THEN 1 ELSE 0 END) AS download_backlog,
                SUM(CASE WHEN content IS NOT NULL AND content != ''
                    AND parsed_at IS NULL
                    AND parse_failed = 0 THEN 1 ELSE 0 END)
                    AS parse_backlog,
                SUM(CASE WHEN sentiment = 'positive' THEN 1 ELSE 0 END)
                    AS sentiment_positive,
                SUM(CASE WHEN sentiment = 'negative' THEN 1 ELSE 0 END)
                    AS sentiment_negative,
                SUM(CASE WHEN sentiment = 'neutral' THEN 1 ELSE 0 END)
                    AS sentiment_neutral,
                SUM(CASE WHEN parsed_at IS NOT NULL
                    AND (summary LIKE '%<%>%'
                         OR title LIKE '%<%>%')
                    THEN 1 ELSE 0 END) AS malformed,
                SUM(CASE WHEN parsed_at IS NOT NULL
                    AND (summary IS NULL OR summary = ''
                         OR categories IS NULL OR categories = ''
                         OR sentiment IS NULL OR sentiment = '')
                    THEN 1 ELSE 0 END) AS missing_fields
            FROM articles
        """)).fetchone()

        result = {
            "total": row[0] or 0,
            "parsed": row[1] or 0,
            "unparsed": row[2] or 0,
            "no_content": row[3] or 0,
            "download_failed": row[4] or 0,
            "parse_failed": row[5] or 0,
            "download_backlog": row[6] or 0,
            "parse_backlog": row[7] or 0,
            "sentiment_positive": row[8] or 0,
            "sentiment_negative": row[9] or 0,
            "sentiment_neutral": row[10] or 0,
            "malformed": row[11] or 0,
            "missing_fields": row[12] or 0,
        }

        # Oldest unparsed article
        oldest = session.execute(text("""
            SELECT MIN(created_at) AS oldest_unparsed_at
            FROM articles
            WHERE content IS NOT NULL
              AND parsed_at IS NULL
              AND parse_failed = 0
        """)).fetchone()
        result["oldest_unparsed_at"] = oldest[0] if oldest else None

        # Articles created today (UTC)
        today = session.execute(text("""
            SELECT COUNT(*) FROM articles
            WHERE DATE(created_at) = CURDATE()
        """)).scalar()
        result["articles_today"] = today or 0

        # Articles created this week (UTC, Monday-based)
        week = session.execute(text("""
            SELECT COUNT(*) FROM articles
            WHERE YEARWEEK(created_at, 1) = YEARWEEK(CURDATE(), 1)
        """)).scalar()
        result["articles_this_week"] = week or 0

        return result


def get_feed_stats(stale_days: int = 7) -> dict:
    """Get consolidated feed statistics in a single query."""
    stale_threshold = (
        datetime.now(timezone.utc) - timedelta(days=stale_days)
    ).isoformat()

    with SessionLocal() as session:
        row = session.execute(
            text("""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN last_fetched_at IS NULL THEN 1 ELSE 0 END)
                    AS never_fetched,
                SUM(CASE WHEN last_fetched_at < :threshold THEN 1 ELSE 0 END)
                    AS stale
            FROM feeds
        """),
            {"threshold": stale_threshold},
        ).fetchone()

        result = {
            "total": row[0] or 0,
            "never_fetched": row[1] or 0,
            "stale": row[2] or 0,
        }

        # Top feeds by article count
        top_rows = session.execute(text("""
            SELECT f.title, f.url, COUNT(a.id) AS article_count
            FROM feeds f
            LEFT JOIN articles a ON f.id = a.feed_id
            GROUP BY f.id
            ORDER BY article_count DESC
            LIMIT 10
        """)).fetchall()

        result["top_feeds"] = [dict(r._mapping) for r in top_rows]
        return result


def get_fetch_stats() -> dict:
    """Get fetch statistics and recent fetch history."""
    with SessionLocal() as session:
        row = session.execute(text("""
            SELECT
                COUNT(*) AS total_runs,
                MAX(started_at) AS last_run_at,
                ROUND(AVG(articles_found), 1) AS avg_articles_per_run
            FROM fetches
        """)).fetchone()

        result = {
            "total_runs": row[0] or 0,
            "last_run_at": row[1],
            "avg_articles_per_run": row[2],
        }

        recent_rows = session.execute(text("""
            SELECT id, started_at, completed_at, status,
                   feeds_fetched, articles_found
            FROM fetches
            ORDER BY started_at DESC
            LIMIT 5
        """)).fetchall()

        result["recent_runs"] = [dict(r._mapping) for r in recent_rows]
        return result


def get_web_stats(hours: int = 48, parsed: bool = False) -> dict:
    """Get homepage display stats within the given time window."""
    threshold = _hours_ago_iso(hours)
    parsed_filter = "AND parsed_at IS NOT NULL" if parsed else ""
    last_updated_column = "MAX(parsed_at)" if parsed else "MAX(created_at)"

    with SessionLocal() as session:
        row = session.execute(
            text(f"""
            SELECT
                COUNT(*) AS live_stories,
                SUM(CASE WHEN fact_check_status IS NOT NULL
                         THEN 1 ELSE 0 END) AS verified,
                COUNT(DISTINCT feed_id) AS sources,
                {last_updated_column} AS last_updated
            FROM articles
            WHERE created_at >= :threshold
              {parsed_filter}
        """),
            {"threshold": threshold},
        ).fetchone()

        result = {
            "live_stories": row[0] or 0,
            "verified": row[1] or 0,
            "sources": row[2] or 0,
            "last_updated": row[3],
        }

        # Count clusters
        cluster_count = len(get_topic_clusters(hours=hours, parsed=parsed))
        result["clusters"] = cluster_count

        return result
