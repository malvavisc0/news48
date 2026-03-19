"""Database module for SQLite operations.

This module provides synchronous database operations for managing feeds, runs,
and articles using sqlite3.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def _utcnow() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def get_connection(db_path: Path):
    """Get a database connection with proper configuration.

    Args:
        db_path: Path to the SQLite database file.

    Yields:
        A sqlite3 connection object with foreign keys and WAL mode enabled.
    """
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("PRAGMA journal_mode = WAL")
        yield db
    finally:
        db.close()


CREATE_FEEDS_TABLE = """
CREATE TABLE IF NOT EXISTS feeds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT UNIQUE NOT NULL,
    title TEXT,
    description TEXT,
    last_fetched_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT
)
"""

CREATE_RUNS_TABLE = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    feeds_fetched INTEGER DEFAULT 0,
    articles_found INTEGER DEFAULT 0
)
"""

CREATE_ARTICLES_TABLE = """
CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    feed_id INTEGER NOT NULL,
    url TEXT UNIQUE NOT NULL,
    title TEXT,
    summary TEXT,
    content TEXT,
    author TEXT,
    published_at DATETIME,
    parsed_at DATETIME,
    sentiment TEXT,
    categories TEXT,
    tags TEXT,
    created_at DATETIME NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(id),
    FOREIGN KEY (feed_id) REFERENCES feeds(id)
)
"""

CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_articles_feed_id ON articles(feed_id)",
    "CREATE INDEX IF NOT EXISTS idx_articles_run_id ON articles(run_id)",
]


def init_database(db_path: Path) -> None:
    """Initialize the database with required tables and indexes.

    Args:
        db_path: Path to the SQLite database file.
    """
    with get_connection(db_path) as db:
        db.execute(CREATE_FEEDS_TABLE)
        db.execute(CREATE_RUNS_TABLE)
        db.execute(CREATE_ARTICLES_TABLE)
        for index_sql in CREATE_INDEXES:
            db.execute(index_sql)
        db.commit()


def seed_feeds(db_path: Path, urls: list[str]) -> int:
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


def get_all_feeds(db_path: Path) -> list[dict]:
    """Get all feeds from the database.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        A list of dicts with feed data (including 'url' and 'id').
    """
    with get_connection(db_path) as db:
        cursor = db.execute("SELECT * FROM feeds")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_feed_by_url(db_path: Path, url: str) -> dict | None:
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
    db_path: Path, feed_id: int, title: str, description: str | None = None
) -> None:
    """Update feed metadata after a successful fetch.

    Args:
        db_path: Path to the SQLite database file.
        feed_id: The ID of the feed to update.
        title: The feed title.
        description: Optional feed description.
    """
    now = _utcnow()
    with get_connection(db_path) as db:
        db.execute(
            """UPDATE feeds
               SET title = ?, description = ?, last_fetched_at = ?,
                   updated_at = ?
               WHERE id = ?""",
            (title, description, now, now, feed_id),
        )
        db.commit()


def get_feed_by_id(db_path: Path, feed_id: int) -> dict | None:
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


def get_feed_article_count(db_path: Path, feed_id: int) -> int:
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


def delete_feed(db_path: Path, feed_id: int) -> bool:
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
    db_path: Path, limit: int = 20, offset: int = 0
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


def get_feed_count(db_path: Path) -> int:
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


# Run operations


def create_run(db_path: Path) -> int:
    """Create a new run and return the run ID.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        The ID of the newly created run.
    """
    now = _utcnow()
    with get_connection(db_path) as db:
        cursor = db.execute(
            "INSERT INTO runs (started_at, status) VALUES (?, ?)",
            (now, "running"),
        )
        db.commit()
        assert cursor.lastrowid is not None
        return cursor.lastrowid


def complete_run(
    db_path: Path, run_id: int, feeds_fetched: int, articles_found: int
) -> None:
    """Mark a run as completed.

    Args:
        db_path: Path to the SQLite database file.
        run_id: The ID of the run to complete.
        feeds_fetched: Number of feeds that were fetched.
        articles_found: Total number of articles found.
    """
    now = _utcnow()
    with get_connection(db_path) as db:
        db.execute(
            """UPDATE runs
               SET completed_at = ?, status = ?, feeds_fetched = ?,
                   articles_found = ?
               WHERE id = ?""",
            (now, "completed", feeds_fetched, articles_found, run_id),
        )
        db.commit()


def fail_run(db_path: Path, run_id: int) -> None:
    """Mark a run as failed.

    Args:
        db_path: Path to the SQLite database file.
        run_id: The ID of the run to mark as failed.
    """
    now = _utcnow()
    with get_connection(db_path) as db:
        db.execute(
            "UPDATE runs SET completed_at = ?, status = ? WHERE id = ?",
            (now, "failed", run_id),
        )
        db.commit()


def list_runs(db_path: Path, limit: int = 20) -> list[dict]:
    """List recent runs ordered by most recent first.

    Args:
        db_path: Path to the SQLite database file.
        limit: Maximum number of runs to return.

    Returns:
        A list of dicts with run data.
    """
    with get_connection(db_path) as db:
        cursor = db.execute(
            "SELECT * FROM runs ORDER BY started_at DESC LIMIT ?", (limit,)
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


# Article operations


def insert_articles(
    db_path: Path | None,
    run_id: int,
    feed_id: int,
    entries: list[dict],
    db: sqlite3.Connection | None = None,
) -> int:
    """Batch insert articles from feed entries, ignoring duplicates by URL.

    Args:
        db_path: Path to the SQLite database file.
            Required if db is not provided.
        run_id: The current run ID.
        feed_id: The feed ID these articles belong to.
        entries: List of dicts with keys: url, title, summary, author,
            published_at.
        db: Optional existing database connection. If provided, uses this
            connection instead of creating a new one. Caller is responsible
            for committing after all inserts.

    Returns:
        Number of new articles inserted.
    """
    now = _utcnow()
    count = 0
    should_close = False

    if db is None:
        if db_path is None:
            raise ValueError("Either db_path or db must be provided")
        db = sqlite3.connect(db_path)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("PRAGMA journal_mode = WAL")
        should_close = True

    try:
        for entry in entries:
            if not entry.get("url"):
                continue  # Skip entries without URLs
            try:
                db.execute(
                    """INSERT INTO articles
                       (run_id, feed_id, url, title, summary, author,
                        published_at, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        run_id,
                        feed_id,
                        entry["url"],
                        entry.get("title"),
                        entry.get("summary"),
                        entry.get("author"),
                        entry.get("published_at"),
                        now,
                    ),
                )
                count += 1
            except sqlite3.IntegrityError:
                pass  # URL already exists
        # Only commit if we own the connection; caller commits otherwise
        if should_close:
            db.commit()
    finally:
        if should_close:
            db.close()

    return count


def update_article(
    db_path: Path,
    article_id: int,
    content: str,
    author: str | None = None,
    published_at: str | None = None,
    sentiment: str | None = None,
    categories: str | None = None,
    tags: str | None = None,
    summary: str | None = None,
    parsed_at: str | None = None,
) -> None:
    """Update an article with parsed content from the parser agent.

    Args:
        db_path: Path to the SQLite database file.
        article_id: The article ID to update.
        content: The parsed article content/summary.
        author: Optionally update the author if parser found a better value.
        published_at: Optionally update published_at if parser found a better
            value.
        sentiment: Optionally update sentiment (positive/negative/neutral).
        categories: Comma-separated categories (e.g., "politics, sports")
        tags: Comma-separated tags (e.g., "pakistan, afghanistan")
        summary: Optionally update the brief summary (max 3 sentences).
    """

    with get_connection(db_path) as db:
        db.execute(
            """UPDATE articles
               SET content = ?, author = COALESCE(?, author),
                   published_at = COALESCE(?, published_at),
                   sentiment = COALESCE(?, sentiment),
                   categories = COALESCE(?, categories),
                   tags = COALESCE(?, tags), summary = COALESCE(?, summary),
                   parsed_at = COALESCE(?, parsed_at)
               WHERE id = ?""",
            (
                content,
                author,
                published_at,
                sentiment,
                categories,
                tags,
                summary,
                parsed_at,
                article_id,
            ),
        )
        db.commit()


def get_unparsed_articles(db_path: Path, limit: int = 50) -> list[dict]:
    """Get articles that have not been parsed yet

    Returns articles ordered by creation date, oldest first.

    Args:
        db_path: Path to the SQLite database file.
        limit: Maximum number of articles to return.

    Returns:
        A list of dicts with article data, including feed_url.
    """
    with get_connection(db_path) as db:
        cursor = db.execute(
            """SELECT a.*, f.url as feed_url
               FROM articles a
               JOIN feeds f ON a.feed_id = f.id
               WHERE a.content IS NOT NULL AND parsed_at IS NULL
               ORDER BY a.created_at ASC
               LIMIT ?""",
            (limit,),
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_empty_articles(db_path: Path, limit: int = 50) -> list[dict]:
    """Get articles that have no content.

    Returns articles ordered by creation date, oldest first.

    Args:
        db_path: Path to the SQLite database file.
        limit: Maximum number of articles to return.

    Returns:
        A list of dicts with article data, including feed_url.
    """
    with get_connection(db_path) as db:
        cursor = db.execute(
            """SELECT a.*, f.url as feed_url
               FROM articles a
               JOIN feeds f ON a.feed_id = f.id
               WHERE a.content IS NULL
               ORDER BY a.created_at ASC
               LIMIT ?""",
            (limit,),
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_article_by_id(db_path: Path, article_id: int) -> dict | None:
    """Look up an article by its ID.

    Args:
        db_path: Path to the SQLite database file.
        article_id: The article ID to look up.

    Returns:
        A dict with article data, or None if not found.
    """
    with get_connection(db_path) as db:
        cursor = db.execute(
            "SELECT * FROM articles WHERE id = ?", (article_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def get_article_by_url(db_path: Path, url: str) -> dict | None:
    """Look up an article by its URL.

    Args:
        db_path: Path to the SQLite database file.
        url: The article URL to look up.

    Returns:
        A dict with article data, or None if not found.
    """
    with get_connection(db_path) as db:
        cursor = db.execute("SELECT * FROM articles WHERE url = ?", (url,))
        row = cursor.fetchone()
        return dict(row) if row else None
