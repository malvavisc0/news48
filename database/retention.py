"""Purge, retention policy, and database health operations."""

from sqlalchemy import text

from database.connection import SessionLocal, _hours_ago_iso


def purge_articles_older_than_hours(
    hours: int = 48,
    dry_run: bool = False,
) -> dict:
    """Purge articles older than specified hours.

    Args:
        hours: Number of hours to use as threshold (default: 48).
        dry_run: If True, only count articles without deleting.

    Returns:
        A dict with purge results:
        - articles_found: Number of articles older than threshold
        - articles_deleted: Number of articles actually deleted
        - threshold_hours: The hours threshold used
        - cutoff_time: The ISO 8601 cutoff time
    """
    with SessionLocal() as session:
        threshold = _hours_ago_iso(hours)

        # Count articles to purge
        articles_found = session.execute(
            text("SELECT COUNT(*) FROM articles WHERE created_at < :threshold"),
            {"threshold": threshold},
        ).scalar()

        articles_deleted = 0
        if not dry_run and articles_found > 0:
            # Delete articles (cascade will handle related records)
            result = session.execute(
                text("DELETE FROM articles WHERE created_at < :threshold"),
                {"threshold": threshold},
            )
            articles_deleted = result.rowcount
            session.commit()

        return {
            "articles_found": articles_found,
            "articles_deleted": articles_deleted,
            "threshold_hours": hours,
            "cutoff_time": threshold,
            "dry_run": dry_run,
        }


def get_retention_policy_stats() -> dict:
    """Get statistics about the 48-hour retention policy.

    Returns:
        A dict with retention policy statistics:
        - total_articles: Total articles in database
        - articles_within_48h: Articles published within last 48 hours
        - articles_expired: Articles older than 48 hours
        - retention_rate: Percentage of articles within 48h window
        - oldest_article: Creation date of oldest article
        - newest_article: Creation date of newest article
    """
    with SessionLocal() as session:
        threshold_48h = _hours_ago_iso(48)

        # Total articles
        total = session.execute(text("SELECT COUNT(*) FROM articles")).scalar()

        # Articles within 48 hours
        within_48h = session.execute(
            text("SELECT COUNT(*) FROM articles WHERE created_at >= :threshold"),
            {"threshold": threshold_48h},
        ).scalar()

        # Articles expired (older than 48 hours)
        expired = session.execute(
            text("SELECT COUNT(*) FROM articles WHERE created_at < :threshold"),
            {"threshold": threshold_48h},
        ).scalar()

        # Oldest and newest articles
        row = session.execute(
            text(
                "SELECT MIN(created_at) as oldest, MAX(created_at) as newest "
                "FROM articles"
            )
        ).fetchone()

        retention_rate = (within_48h / total * 100) if total > 0 else 0

        return {
            "total_articles": total,
            "articles_within_48h": within_48h,
            "articles_expired": expired,
            "retention_rate": round(retention_rate, 2),
            "oldest_article": row[0] if row else None,
            "newest_article": row[1] if row else None,
            "threshold_hours": 48,
        }


def check_database_health() -> dict:
    """Check database health and connectivity.

    Returns:
        A dict with health check results:
        - is_connected: Whether database is accessible
        - db_size_mb: Database size in megabytes
        - table_counts: Number of rows in each table
        - integrity_ok: Whether database integrity check passed
    """
    health = {
        "is_connected": False,
        "db_size_mb": 0,
        "table_counts": {},
        "integrity_ok": False,
    }

    try:
        with SessionLocal() as session:
            # Check connectivity
            session.execute(text("SELECT 1"))
            health["is_connected"] = True

            # Get table counts
            for table in ["feeds", "fetches", "articles", "claims"]:
                count = session.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
                health["table_counts"][table] = count

            # MySQL-specific health: table status for size
            rows = session.execute(text("SHOW TABLE STATUS")).fetchall()
            total_size = sum((r.Data_length or 0) + (r.Index_length or 0) for r in rows)
            health["db_size_mb"] = round(total_size / (1024 * 1024), 2)

            # Integrity check via CHECK TABLE
            check = session.execute(
                text("CHECK TABLE articles, feeds, fetches, claims")
            ).fetchall()
            health["integrity_ok"] = all(
                row[3] != "error" for row in check  # Msg_type column
            )

    except Exception as e:
        health["error"] = str(e)

    return health
