"""Feed CRUD operations."""

import sqlite3

from database.connection import _utcnow, get_connection


def seed_feeds(db_path, urls: list[str]) -> int:
    """Insert feeds from seed file, ignoring duplicates.

    Args:
        db_path: Path to the SQLite database file.
        urls: List of feed URLs to insert.

    Returns:
        Number of new feeds inserted.
    """
    now = _utcnow()
    count = 0
    with get_connection(db_path) as db:
        for url in urls:
            try:
                db.execute(
                    "INSERT INTO feeds (url, created_at) VALUES (?, ?)",
                    (url, now),
                )
                count += 1
            except sqlite3.IntegrityError:
                pass  # URL already exists
        db.commit()
    return count


def get_all_feeds(db_path, feed_domain: str | None = None) -> list[dict]:
    """Get all feeds from the database, optionally filtered by domain.

    Args:
        db_path: Path to the SQLite database file.
        feed_domain: Optional domain to filter feeds by (matched against
            the feed URL using LIKE).

    Returns:
        A list of dicts with feed data (including 'url' and 'id').
    """
    with get_connection(db_path) as db:
        if feed_domain:
            cursor = db.execute(
                "SELECT * FROM feeds WHERE url LIKE '%' || ? || '%'",
                (feed_domain,),
            )
        else:
            cursor = db.execute("SELECT * FROM feeds")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_feed_by_url(db_path, url: str) -> dict | None:
    """Look up a feed by its URL.

    Args:
        db_path: Path to the SQLite database file.
        url: The feed URL to look up.

    Returns:
        A dict with feed data, or None if not found.
    """
    with get_connection(db_path) as db:
        cursor = db.execute("SELECT * FROM feeds WHERE url = ?", (url,))
        row = cursor.fetchone()
        return dict(row) if row else None


def update_feed_metadata(
    db_path,
    feed_id: int,
    title: str,
    description: str | None = None,
    icon_url: str | None = None,
    favicon_url: str | None = None,
) -> None:
    """Update feed metadata after a successful fetch.

    Args:
        db_path: Path to the SQLite database file.
        feed_id: The ID of the feed to update.
        title: The feed title.
        description: Optional feed description.
        icon_url: Optional URL of the feed icon/logo.
        favicon_url: Optional URL of the feed favicon.
    """
    now = _utcnow()
    with get_connection(db_path) as db:
        db.execute(
            """UPDATE feeds
               SET title = ?, description = ?, last_fetched_at = ?,
                   updated_at = ?,
                   icon_url = COALESCE(?, icon_url),
                   favicon_url = COALESCE(?, favicon_url)
               WHERE id = ?""",
            (title, description, now, now, icon_url, favicon_url, feed_id),
        )
        db.commit()


def get_feed_by_id(db_path, feed_id: int) -> dict | None:
    """Look up a feed by its ID.

    Args:
        db_path: Path to the SQLite database file.
        feed_id: The feed ID to look up.

    Returns:
        A dict with feed data, or None if not found.
    """
    with get_connection(db_path) as db:
        cursor = db.execute("SELECT * FROM feeds WHERE id = ?", (feed_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_feed_article_count(db_path, feed_id: int) -> int:
    """Get the number of articles for a specific feed.

    Args:
        db_path: Path to the SQLite database file.
        feed_id: The feed ID to count articles for.

    Returns:
        Number of articles associated with the feed.
    """
    with get_connection(db_path) as db:
        cursor = db.execute(
            "SELECT COUNT(*) FROM articles WHERE feed_id = ?", (feed_id,)
        )
        row = cursor.fetchone()
        return row[0] if row else 0


def delete_feed(db_path, feed_id: int) -> bool:
    """Delete a feed and its associated articles by feed ID.

    Args:
        db_path: Path to the SQLite database file.
        feed_id: The ID of the feed to delete.

    Returns:
        True if the feed was deleted, False if not found.
    """
    with get_connection(db_path) as db:
        # Delete associated articles first to avoid FK constraint errors
        db.execute("DELETE FROM articles WHERE feed_id = ?", (feed_id,))
        cursor = db.execute("DELETE FROM feeds WHERE id = ?", (feed_id,))
        db.commit()
        return cursor.rowcount > 0


def get_feeds_paginated(
    db_path, limit: int = 20, offset: int = 0
) -> list[dict]:
    """Get feeds with server-side pagination.

    Args:
        db_path: Path to the SQLite database file.
        limit: Maximum number of feeds to return.
        offset: Number of feeds to skip.

    Returns:
        A list of dicts with feed data.
    """
    with get_connection(db_path) as db:
        cursor = db.execute(
            "SELECT * FROM feeds ORDER BY id LIMIT ? OFFSET ?",
            (limit, offset),
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_feed_count(db_path) -> int:
    """Get total number of feeds in the database.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        Total number of feeds.
    """
    with get_connection(db_path) as db:
        cursor = db.execute("SELECT COUNT(*) FROM feeds")
        row = cursor.fetchone()
        return row[0] if row else 0
