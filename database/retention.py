"""Purge, retention policy, and database health operations."""

import sqlite3

from database.connection import _hours_ago_iso, get_connection


def purge_articles_older_than_hours(
    db_path,
    hours: int = 48,
    dry_run: bool = False,
) -> dict:
    """Purge articles older than specified hours.

    Args:
        db_path: Path to the SQLite database file.
        hours: Number of hours to use as threshold (default: 48).
        dry_run: If True, only count articles without deleting.

    Returns:
        A dict with purge results:
        - articles_found: Number of articles older than threshold
        - articles_deleted: Number of articles actually deleted
        - threshold_hours: The hours threshold used
        - cutoff_time: The ISO 8601 cutoff time
    """
    with get_connection(db_path) as db:
        threshold = _hours_ago_iso(hours)

        # Count articles to purge
        cursor = db.execute(
            "SELECT COUNT(*) as cnt FROM articles WHERE created_at < ?",
            (threshold,),
        )
        articles_found = cursor.fetchone()["cnt"]

        articles_deleted = 0
        if not dry_run and articles_found > 0:
            # Delete articles (cascade will handle related records)
            cursor = db.execute(
                "DELETE FROM articles WHERE created_at < ?",
                (threshold,),
            )
            articles_deleted = cursor.rowcount
            db.commit()

        return {
            "articles_found": articles_found,
            "articles_deleted": articles_deleted,
            "threshold_hours": hours,
            "cutoff_time": threshold,
            "dry_run": dry_run,
        }


def get_retention_policy_stats(db_path) -> dict:
    """Get statistics about the 48-hour retention policy.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        A dict with retention policy statistics:
        - total_articles: Total articles in database
        - articles_within_48h: Articles published within last 48 hours
        - articles_expired: Articles older than 48 hours
        - retention_rate: Percentage of articles within 48h window
        - oldest_article: Creation date of oldest article
        - newest_article: Creation date of newest article
    """
    with get_connection(db_path) as db:
        threshold_48h = _hours_ago_iso(48)

        # Total articles
        cursor = db.execute("SELECT COUNT(*) as cnt FROM articles")
        total = cursor.fetchone()["cnt"]

        # Articles within 48 hours
        cursor = db.execute(
            "SELECT COUNT(*) as cnt FROM articles WHERE created_at >= ?",
            (threshold_48h,),
        )
        within_48h = cursor.fetchone()["cnt"]

        # Articles expired (older than 48 hours)
        cursor = db.execute(
            "SELECT COUNT(*) as cnt FROM articles WHERE created_at < ?",
            (threshold_48h,),
        )
        expired = cursor.fetchone()["cnt"]

        # Oldest and newest articles
        cursor = db.execute("""SELECT MIN(created_at) as oldest,
                      MAX(created_at) as newest
               FROM articles""")
        dates = cursor.fetchone()

        retention_rate = (within_48h / total * 100) if total > 0 else 0

        return {
            "total_articles": total,
            "articles_within_48h": within_48h,
            "articles_expired": expired,
            "retention_rate": round(retention_rate, 2),
            "oldest_article": dates["oldest"],
            "newest_article": dates["newest"],
            "threshold_hours": 48,
        }


def check_database_health(db_path) -> dict:
    """Check database health and connectivity.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        A dict with health check results:
        - is_connected: Whether database is accessible
        - db_size_mb: Database size in megabytes
        - table_counts: Number of rows in each table
        - integrity_ok: Whether database integrity check passed
        - wal_mode: Whether WAL mode is enabled
    """
    health = {
        "is_connected": False,
        "db_size_mb": 0,
        "table_counts": {},
        "integrity_ok": False,
        "wal_mode": False,
    }

    try:
        # Check if database file exists and is accessible
        if not db_path.exists():
            return health

        health["db_size_mb"] = round(db_path.stat().st_size / (1024 * 1024), 2)

        with get_connection(db_path) as db:
            health["is_connected"] = True

            # Check WAL mode
            cursor = db.execute("PRAGMA journal_mode")
            health["wal_mode"] = cursor.fetchone()[0] == "wal"

            # Get table counts
            for table in ["feeds", "fetches", "articles"]:
                cursor = db.execute(f"SELECT COUNT(*) as cnt FROM {table}")
                health["table_counts"][table] = cursor.fetchone()["cnt"]

            # Check FTS health
            try:
                cursor = db.execute("SELECT COUNT(*) FROM articles_fts")
                health["table_counts"]["articles_fts"] = cursor.fetchone()[0]
            except sqlite3.OperationalError:
                health["table_counts"]["articles_fts"] = None

            # Check integrity
            cursor = db.execute("PRAGMA integrity_check")
            result = cursor.fetchone()[0]
            health["integrity_ok"] = result == "ok"

    except Exception as e:
        health["error"] = str(e)

    return health
