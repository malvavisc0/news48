"""Database module for SQLite operations.

This module provides synchronous database operations for managing feeds, runs,
and articles using sqlite3.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
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

CREATE_FETCHES_TABLE = """
CREATE TABLE IF NOT EXISTS fetches (
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
    fetch_id INTEGER NOT NULL,
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
    download_failed INTEGER NOT NULL DEFAULT 0,
    download_error TEXT,
    parse_failed INTEGER NOT NULL DEFAULT 0,
    parse_error TEXT,
    countries TEXT,
    fact_check_status TEXT,
    fact_check_result TEXT,
    fact_checked_at DATETIME,
    processing_status TEXT,
    processing_owner TEXT,
    processing_started_at DATETIME,
    created_at DATETIME NOT NULL,
    FOREIGN KEY (fetch_id) REFERENCES fetches(id),
    FOREIGN KEY (feed_id) REFERENCES feeds(id)
)
"""

CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_articles_feed_id ON articles(feed_id)",
    "CREATE INDEX IF NOT EXISTS idx_articles_fetch_id ON articles(fetch_id)",
    (
        "CREATE INDEX IF NOT EXISTS idx_articles_download_failed "
        "ON articles(download_failed)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS idx_articles_parse_failed "
        "ON articles(parse_failed)"
    ),
]


# Migrations for existing databases that lack newer columns.
_MIGRATIONS = [
    "ALTER TABLE articles ADD COLUMN fact_check_status TEXT",
    "ALTER TABLE articles ADD COLUMN fact_check_result TEXT",
    "ALTER TABLE articles ADD COLUMN fact_checked_at DATETIME",
    "ALTER TABLE articles ADD COLUMN processing_status TEXT",
    "ALTER TABLE articles ADD COLUMN processing_owner TEXT",
    "ALTER TABLE articles ADD COLUMN processing_started_at DATETIME",
]

_VALID_PROCESSING_ACTIONS = {"download", "parse", "fact_check"}
_CLAIM_TIMEOUT_MINUTES = 30


def _claim_cutoff(minutes: int = _CLAIM_TIMEOUT_MINUTES) -> str:
    """Return the cutoff timestamp for stale processing claims."""
    return (
        datetime.now(timezone.utc) - timedelta(minutes=minutes)
    ).isoformat()


def init_database(db_path: Path) -> None:
    """Initialize the database with required tables and indexes.

    Also applies any pending migrations for existing databases.

    Args:
        db_path: Path to the SQLite database file.
    """
    with get_connection(db_path) as db:
        db.execute(CREATE_FEEDS_TABLE)
        db.execute(CREATE_FETCHES_TABLE)
        db.execute(CREATE_ARTICLES_TABLE)
        for index_sql in CREATE_INDEXES:
            db.execute(index_sql)
        # Apply migrations (safe to re-run; duplicate columns are ignored)
        for migration in _MIGRATIONS:
            try:
                db.execute(migration)
            except sqlite3.OperationalError:
                pass  # Column already exists
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


def get_all_feeds(db_path: Path, feed_domain: str | None = None) -> list[dict]:
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


# Fetch operations


def create_fetch(db_path: Path) -> int:
    """Create a new fetch and return the fetch ID.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        The ID of the newly created fetch.
    """
    now = _utcnow()
    with get_connection(db_path) as db:
        cursor = db.execute(
            "INSERT INTO fetches (started_at, status) VALUES (?, ?)",
            (now, "running"),
        )
        db.commit()
        assert cursor.lastrowid is not None
        return cursor.lastrowid


def complete_fetch(
    db_path: Path, fetch_id: int, feeds_fetched: int, articles_found: int
) -> None:
    """Mark a fetch as completed.

    Args:
        db_path: Path to the SQLite database file.
        fetch_id: The ID of the fetch to complete.
        feeds_fetched: Number of feeds that were fetched.
        articles_found: Total number of articles found.
    """
    now = _utcnow()
    with get_connection(db_path) as db:
        db.execute(
            """UPDATE fetches
               SET completed_at = ?, status = ?, feeds_fetched = ?,
                   articles_found = ?
               WHERE id = ?""",
            (now, "completed", feeds_fetched, articles_found, fetch_id),
        )
        db.commit()


def fail_fetch(db_path: Path, fetch_id: int) -> None:
    """Mark a fetch as failed.

    Args:
        db_path: Path to the SQLite database file.
        fetch_id: The ID of the fetch to mark as failed.
    """
    now = _utcnow()
    with get_connection(db_path) as db:
        db.execute(
            "UPDATE fetches SET completed_at = ?, status = ? WHERE id = ?",
            (now, "failed", fetch_id),
        )
        db.commit()


def list_fetches(db_path: Path, limit: int = 20) -> list[dict]:
    """List recent fetches ordered by most recent first.

    Args:
        db_path: Path to the SQLite database file.
        limit: Maximum number of fetches to return.

    Returns:
        A list of dicts with fetch data.
    """
    with get_connection(db_path) as db:
        cursor = db.execute(
            "SELECT * FROM fetches ORDER BY started_at DESC LIMIT ?", (limit,)
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


# Article operations


def insert_articles(
    db_path: Path | None,
    fetch_id: int,
    feed_id: int,
    entries: list[dict],
    db: sqlite3.Connection | None = None,
) -> int:
    """Batch insert articles from feed entries, ignoring duplicates by URL.

    Args:
        db_path: Path to the SQLite database file.
            Required if db is not provided.
        fetch_id: The current fetch ID.
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
                       (fetch_id, feed_id, url, title, summary, author,
                        published_at, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        fetch_id,
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
    countries: str | None = None,
    title: str | None = None,
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
        countries: Comma-separated countries (e.g., "Pakistan, Afghanistan")
        title: Optionally update the title with improved version.
    """
    if sentiment:
        sentiment = sentiment.lower()
    if categories:
        categories = categories.lower()
    if tags:
        tags = tags.lower()
    if countries:
        countries = countries.lower()
    with get_connection(db_path) as db:
        db.execute(
            """UPDATE articles
               SET content = ?, author = COALESCE(?, author),
                   published_at = COALESCE(?, published_at),
                   sentiment = COALESCE(?, sentiment),
                   categories = COALESCE(?, categories),
                   tags = COALESCE(?, tags), summary = COALESCE(?, summary),
                   parsed_at = COALESCE(?, parsed_at),
                   countries = COALESCE(?, countries),
                   title = COALESCE(?, title)
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
                countries,
                title,
                article_id,
            ),
        )
        db.commit()


def update_article_fact_check(
    db_path: Path,
    article_id: int,
    status: str,
    result: str | None = None,
    force: bool = False,
) -> bool:
    """Update the fact-check fields of an article.

    Args:
        db_path: Path to the SQLite database file.
        article_id: The article ID to update.
        status: Fact-check verdict. One of: verified, disputed,
            unverifiable, mixed.
        result: Optional free-text summary of the fact-check assessment.

    Returns:
        True if the article was found and updated, False otherwise.
    """
    valid_statuses = {"verified", "disputed", "unverifiable", "mixed"}
    if status.lower() not in valid_statuses:
        raise ValueError(
            f"Invalid fact_check_status '{status}'. "
            f"Valid: {', '.join(sorted(valid_statuses))}"
        )
    now = _utcnow()
    with get_connection(db_path) as db:
        if force:
            cursor = db.execute(
                """UPDATE articles
                   SET fact_check_status = ?,
                       fact_check_result = ?,
                       fact_checked_at = ?
                   WHERE id = ?""",
                (status.lower(), result, now, article_id),
            )
        else:
            cursor = db.execute(
                """UPDATE articles
                   SET fact_check_status = ?,
                       fact_check_result = ?,
                       fact_checked_at = ?
                   WHERE id = ?
                     AND fact_check_status IS NULL""",
                (status.lower(), result, now, article_id),
            )
        db.commit()
        return cursor.rowcount > 0


def claim_articles_for_processing(
    db_path: Path,
    article_ids: list[int],
    action: str,
    owner: str,
    *,
    force: bool = False,
    stale_after_minutes: int = _CLAIM_TIMEOUT_MINUTES,
) -> list[int]:
    """Claim articles for a processing action.

    Claims are used to reduce duplicate work across concurrent processes.

    Args:
        db_path: Path to the SQLite database file.
        article_ids: Candidate article IDs to claim.
        action: One of download, parse, or fact_check.
        owner: Identifier for the claiming process.
        force: If True, overwrite existing claims.
        stale_after_minutes: Minutes after which a claim is considered stale.

    Returns:
        The subset of article IDs successfully claimed for the owner.
    """
    if not article_ids:
        return []
    if action not in _VALID_PROCESSING_ACTIONS:
        raise ValueError(
            f"Invalid processing action '{action}'. "
            f"Valid: {', '.join(sorted(_VALID_PROCESSING_ACTIONS))}"
        )

    placeholders = ", ".join("?" for _ in article_ids)
    now = _utcnow()
    cutoff = _claim_cutoff(stale_after_minutes)

    with get_connection(db_path) as db:
        db.execute("BEGIN IMMEDIATE")
        params: list = [action, owner, now, *article_ids]
        sql = f"""UPDATE articles
                  SET processing_status = ?,
                      processing_owner = ?,
                      processing_started_at = ?
                  WHERE id IN ({placeholders})"""
        if not force:
            sql += """
                    AND (
                        processing_status IS NULL
                        OR processing_started_at IS NULL
                        OR processing_started_at < ?
                        OR processing_owner = ?
                    )"""
            params.extend([cutoff, owner])
        db.execute(sql, params)

        cursor = db.execute(
            f"""SELECT id FROM articles
                   WHERE id IN ({placeholders})
                     AND processing_status = ?
                     AND processing_owner = ?""",
            [*article_ids, action, owner],
        )
        claimed = [int(row[0]) for row in cursor.fetchall()]
        db.commit()
        return claimed


def clear_article_processing_claim(
    db_path: Path,
    article_id: int,
    owner: str | None = None,
) -> None:
    """Clear the processing claim for an article.

    Args:
        db_path: Path to the SQLite database file.
        article_id: Article ID to release.
        owner: Optional owner restriction. If provided, only release claims
            currently held by that owner.
    """
    with get_connection(db_path) as db:
        if owner is None:
            db.execute(
                """UPDATE articles
                   SET processing_status = NULL,
                       processing_owner = NULL,
                       processing_started_at = NULL
                   WHERE id = ?""",
                (article_id,),
            )
        else:
            db.execute(
                """UPDATE articles
                   SET processing_status = NULL,
                       processing_owner = NULL,
                       processing_started_at = NULL
                   WHERE id = ? AND processing_owner = ?""",
                (article_id, owner),
            )
        db.commit()


def get_unparsed_articles(
    db_path: Path, limit: int = 50, feed_domain: str | None = None
) -> list[dict]:
    """Get articles that have not been parsed yet.

    Returns articles ordered by creation date, oldest first.

    Args:
        db_path: Path to the SQLite database file.
        limit: Maximum number of articles to return.
        feed_domain: Optional domain to filter by feed URL.

    Returns:
        A list of dicts with article data, including feed_url.
    """
    with get_connection(db_path) as db:
        if feed_domain:
            cursor = db.execute(
                """SELECT a.*, f.url as feed_url
                   FROM articles a
                   JOIN feeds f ON a.feed_id = f.id
                   WHERE a.content IS NOT NULL
                     AND parsed_at IS NULL
                     AND a.parse_failed = 0
                     AND f.url LIKE '%' || ? || '%'
                   ORDER BY a.created_at ASC
                   LIMIT ?""",
                (feed_domain, limit),
            )
        else:
            cursor = db.execute(
                """SELECT a.*, f.url as feed_url
                   FROM articles a
                   JOIN feeds f ON a.feed_id = f.id
                   WHERE a.content IS NOT NULL
                     AND parsed_at IS NULL
                     AND a.parse_failed = 0
                   ORDER BY a.created_at ASC
                   LIMIT ?""",
                (limit,),
            )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_parse_failed_articles(
    db_path: Path, limit: int = 50, feed_domain: str | None = None
) -> list[dict]:
    """Get articles that have failed parsing.

    Returns articles ordered by creation date, oldest first.

    Args:
        db_path: Path to the SQLite database file.
        limit: Maximum number of articles to return.
        feed_domain: Optional domain to filter by feed URL.

    Returns:
        A list of dicts with article data, including feed_url.
    """
    with get_connection(db_path) as db:
        if feed_domain:
            cursor = db.execute(
                """SELECT a.*, f.url as feed_url
                   FROM articles a
                   JOIN feeds f ON a.feed_id = f.id
                   WHERE a.parse_failed = 1
                     AND f.url LIKE '%' || ? || '%'
                   ORDER BY a.created_at ASC
                   LIMIT ?""",
                (feed_domain, limit),
            )
        else:
            cursor = db.execute(
                """SELECT a.*, f.url as feed_url
                   FROM articles a
                   JOIN feeds f ON a.feed_id = f.id
                   WHERE a.parse_failed = 1
                   ORDER BY a.created_at ASC
                   LIMIT ?""",
                (limit,),
            )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_empty_articles(
    db_path: Path, limit: int = 50, feed_domain: str | None = None
) -> list[dict]:
    """Get articles that have no content.

    Returns articles ordered by creation date, oldest first.

    Args:
        db_path: Path to the SQLite database file.
        limit: Maximum number of articles to return.
        feed_domain: Optional domain to filter by feed URL.

    Returns:
        A list of dicts with article data, including feed_url.
    """
    with get_connection(db_path) as db:
        if feed_domain:
            cursor = db.execute(
                """SELECT a.*, f.url as feed_url
                   FROM articles a
                   JOIN feeds f ON a.feed_id = f.id
                   WHERE a.content IS NULL
                     AND a.download_failed = 0
                     AND f.url LIKE '%' || ? || '%'
                   ORDER BY a.created_at ASC
                   LIMIT ?""",
                (feed_domain, limit),
            )
        else:
            cursor = db.execute(
                """SELECT a.*, f.url as feed_url
                   FROM articles a
                   JOIN feeds f ON a.feed_id = f.id
                   WHERE a.content IS NULL
                     AND a.download_failed = 0
                   ORDER BY a.created_at ASC
                   LIMIT ?""",
                (limit,),
            )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_download_failed_articles(
    db_path: Path, limit: int = 50, feed_domain: str | None = None
) -> list[dict]:
    """Get articles where download_failed = 1.

    Returns articles ordered by creation date, oldest first.

    Args:
        db_path: Path to the SQLite database file.
        limit: Maximum number of articles to return.
        feed_domain: Optional domain to filter by feed URL.

    Returns:
        A list of dicts with article data, including feed_url.
    """
    with get_connection(db_path) as db:
        if feed_domain:
            cursor = db.execute(
                """SELECT a.*, f.url as feed_url
                   FROM articles a
                   JOIN feeds f ON a.feed_id = f.id
                   WHERE a.download_failed = 1
                     AND f.url LIKE '%' || ? || '%'
                   ORDER BY a.created_at ASC
                   LIMIT ?""",
                (feed_domain, limit),
            )
        else:
            cursor = db.execute(
                """SELECT a.*, f.url as feed_url
                   FROM articles a
                   JOIN feeds f ON a.feed_id = f.id
                   WHERE a.download_failed = 1
                   ORDER BY a.created_at ASC
                   LIMIT ?""",
                (limit,),
            )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def reset_article_download(db_path: Path, article_id: int) -> None:
    """Reset download_failed flag and clear download_error for an article.

    Args:
        db_path: Path to the SQLite database file.
        article_id: The ID of the article to reset.
    """
    with get_connection(db_path) as db:
        db.execute(
            """UPDATE articles
               SET download_failed = 0, download_error = NULL
               WHERE id = ?""",
            (article_id,),
        )
        db.commit()


def get_articles_paginated(
    db_path: Path,
    limit: int = 20,
    offset: int = 0,
    feed_domain: str | None = None,
    status: str | None = None,
) -> tuple[list[dict], int]:
    """Return filtered, paginated articles and total count.

    Args:
        db_path: Path to the SQLite database file.
        limit: Maximum number of articles to return.
        offset: Number of articles to skip.
        feed_domain: Optional domain to filter by feed URL.
        status: Optional status filter. One of: empty, downloaded,
            parsed, download-failed, parse-failed.

    Returns:
        A tuple of (articles list, total count).
    """
    status_conditions = {
        "empty": "a.content IS NULL AND a.download_failed = 0",
        "downloaded": (
            "a.content IS NOT NULL AND a.parsed_at IS NULL "
            "AND a.parse_failed = 0"
        ),
        "parsed": "a.parsed_at IS NOT NULL",
        "download-failed": "a.download_failed = 1",
        "parse-failed": "a.parse_failed = 1",
        "fact-checked": "a.fact_check_status IS NOT NULL",
        "fact-unchecked": (
            "a.parsed_at IS NOT NULL " "AND a.fact_check_status IS NULL"
        ),
    }

    where_clauses = []
    params: list = []

    if feed_domain:
        where_clauses.append("f.url LIKE '%' || ? || '%'")
        params.append(feed_domain)

    if status and status in status_conditions:
        where_clauses.append(status_conditions[status])

    where_sql = ""
    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)

    with get_connection(db_path) as db:
        # Get total count
        count_cursor = db.execute(
            f"""SELECT COUNT(*) FROM articles a
                JOIN feeds f ON a.feed_id = f.id
                {where_sql}""",
            params,
        )
        total = count_cursor.fetchone()[0]

        # Get paginated results
        cursor = db.execute(
            f"""SELECT a.id, a.url, a.title, f.url as feed_url,
                       a.content IS NOT NULL as has_content,
                       a.parsed_at IS NOT NULL as is_parsed,
                       a.download_failed, a.parse_failed,
                       a.fact_check_status,
                       a.processing_status,
                       a.processing_owner,
                       a.processing_started_at,
                       a.created_at, a.published_at
                FROM articles a
                JOIN feeds f ON a.feed_id = f.id
                {where_sql}
                ORDER BY a.created_at DESC
                LIMIT ? OFFSET ?""",
            [*params, limit, offset],
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows], total


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


def mark_article_download_failed(
    db_path: Path, article_id: int, error: str
) -> None:
    """Mark an article as having a failed download.

    Args:
        db_path: Path to the SQLite database file.
        article_id: The ID of the article to mark.
        error: The error message describing the failure.
    """
    with get_connection(db_path) as db:
        db.execute(
            """UPDATE articles
               SET download_failed = 1, download_error = ?
               WHERE id = ?""",
            (error, article_id),
        )
        db.commit()


def mark_article_parse_failed(
    db_path: Path, article_id: int, error: str
) -> None:
    """Mark an article as having a failed parse.

    Args:
        db_path: Path to the SQLite database file.
        article_id: The ID of the article to mark.
        error: The error message describing the failure.
    """
    with get_connection(db_path) as db:
        db.execute(
            """UPDATE articles
               SET parse_failed = 1, parse_error = ?
               WHERE id = ?""",
            (error, article_id),
        )
        db.commit()


def reset_article_parse(db_path: Path, article_id: int) -> None:
    """Reset parse_failed flag and clear parse_error for an article.

    Args:
        db_path: Path to the SQLite database file.
        article_id: The ID of the article to reset.
    """
    with get_connection(db_path) as db:
        db.execute(
            """UPDATE articles
               SET parse_failed = 0, parse_error = NULL, parsed_at = NULL
               WHERE id = ?""",
            (article_id,),
        )
        db.commit()


def delete_article(db_path: Path, article_id: int) -> bool:
    """Delete an article by ID.

    Args:
        db_path: Path to the SQLite database file.
        article_id: The ID of the article to delete.

    Returns:
        True if the article was deleted, False if not found.
    """
    with get_connection(db_path) as db:
        cursor = db.execute("DELETE FROM articles WHERE id = ?", (article_id,))
        db.commit()
        return cursor.rowcount > 0


# Stats operations


def get_article_stats(db_path: Path) -> dict:
    """Get consolidated article statistics in a single query.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        A dict with keys: total, parsed, unparsed, no_content,
        download_failed, parse_failed, download_backlog, parse_backlog,
        sentiment_positive, sentiment_negative, sentiment_neutral,
        oldest_unparsed_at, articles_today, articles_this_week.
    """
    with get_connection(db_path) as db:
        cursor = db.execute("""SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN parsed_at IS NOT NULL THEN 1 ELSE 0 END)
                    AS parsed,
                SUM(CASE WHEN parsed_at IS NULL THEN 1 ELSE 0 END)
                    AS unparsed,
                SUM(CASE WHEN content IS NULL OR content = ''
                    THEN 1 ELSE 0 END)
                    AS no_content,
                SUM(CASE WHEN download_failed = 1 THEN 1 ELSE 0 END)
                    AS download_failed,
                SUM(CASE WHEN parse_failed = 1 THEN 1 ELSE 0 END)
                    AS parse_failed,
                SUM(CASE WHEN content IS NULL AND download_failed = 0
                    THEN 1 ELSE 0 END) AS download_backlog,
                SUM(CASE WHEN content IS NOT NULL AND parsed_at IS NULL
                    AND parse_failed = 0 THEN 1 ELSE 0 END)
                    AS parse_backlog,
                SUM(CASE WHEN sentiment = 'positive' THEN 1 ELSE 0 END)
                    AS sentiment_positive,
                SUM(CASE WHEN sentiment = 'negative' THEN 1 ELSE 0 END)
                    AS sentiment_negative,
                SUM(CASE WHEN sentiment = 'neutral' THEN 1 ELSE 0 END)
                    AS sentiment_neutral
            FROM articles""")
        row = dict(cursor.fetchone())

        # Oldest unparsed article
        cursor = db.execute("""SELECT MIN(created_at) AS oldest_unparsed_at
               FROM articles
               WHERE content IS NOT NULL
                 AND parsed_at IS NULL
                 AND parse_failed = 0""")
        oldest = cursor.fetchone()
        row["oldest_unparsed_at"] = (
            oldest["oldest_unparsed_at"] if oldest else None
        )

        # Articles created today (UTC)
        cursor = db.execute("""SELECT COUNT(*) AS cnt FROM articles
               WHERE created_at >= date('now')""")
        row["articles_today"] = cursor.fetchone()["cnt"]

        # Articles created this week (UTC, Monday-based)
        cursor = db.execute("""SELECT COUNT(*) AS cnt FROM articles
               WHERE created_at >= date('now', 'weekday 1', '-7 days')""")
        row["articles_this_week"] = cursor.fetchone()["cnt"]

        return row


def get_feed_stats(db_path: Path, stale_days: int = 7) -> dict:
    """Get consolidated feed statistics in a single query.

    Args:
        db_path: Path to the SQLite database file.
        stale_days: Number of days after which a feed is considered stale.

    Returns:
        A dict with keys: total, never_fetched, stale, top_feeds.
        top_feeds is a list of dicts with title, url, article_count.
    """
    with get_connection(db_path) as db:
        stale_threshold = (
            datetime.now(timezone.utc) - timedelta(days=stale_days)
        ).isoformat()

        cursor = db.execute(
            """SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN last_fetched_at IS NULL THEN 1 ELSE 0 END)
                    AS never_fetched,
                SUM(CASE WHEN last_fetched_at < ? THEN 1 ELSE 0 END)
                    AS stale
            FROM feeds""",
            (stale_threshold,),
        )
        row = dict(cursor.fetchone())

        # Top feeds by article count
        cursor = db.execute(
            """SELECT f.title, f.url, COUNT(a.id) AS article_count
               FROM feeds f
               LEFT JOIN articles a ON f.id = a.feed_id
               GROUP BY f.id
               ORDER BY article_count DESC
               LIMIT 10"""
        )
        row["top_feeds"] = [dict(r) for r in cursor.fetchall()]

        return row


def get_fetch_stats(db_path: Path) -> dict:
    """Get fetch statistics and recent fetch history.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        A dict with keys: total_runs, last_run_at, avg_articles_per_run,
        recent_runs (list of dicts).
    """
    with get_connection(db_path) as db:
        cursor = db.execute("""SELECT
                COUNT(*) AS total_runs,
                MAX(started_at) AS last_run_at,
                ROUND(AVG(articles_found), 1) AS avg_articles_per_run
            FROM fetches""")
        row = dict(cursor.fetchone())

        cursor = db.execute("""SELECT id, started_at, completed_at, status,
                      feeds_fetched, articles_found
               FROM fetches
               ORDER BY started_at DESC
               LIMIT 5""")
        row["recent_runs"] = [dict(r) for r in cursor.fetchall()]

        return row


# Retention policy operations


def get_articles_older_than_hours(
    db_path: Path, hours: int = 48
) -> list[dict]:
    """Get articles older than specified hours.

    Args:
        db_path: Path to the SQLite database file.
        hours: Number of hours to use as threshold (default: 48).

    Returns:
        A list of dicts with article data for articles older than threshold.
    """
    with get_connection(db_path) as db:
        threshold = (
            datetime.now(timezone.utc) - timedelta(hours=hours)
        ).isoformat()

        cursor = db.execute(
            """SELECT a.*, f.url as feed_url
               FROM articles a
               JOIN feeds f ON a.feed_id = f.id
               WHERE a.created_at < ?
               ORDER BY a.created_at ASC""",
            (threshold,),
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def purge_articles_older_than_hours(
    db_path: Path,
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
        threshold = (
            datetime.now(timezone.utc) - timedelta(hours=hours)
        ).isoformat()

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


def get_retention_policy_stats(db_path: Path) -> dict:
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
        threshold_48h = (
            datetime.now(timezone.utc) - timedelta(hours=48)
        ).isoformat()

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


def check_database_health(db_path: Path) -> dict:
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

            # Check integrity
            cursor = db.execute("PRAGMA integrity_check")
            result = cursor.fetchone()[0]
            health["integrity_ok"] = result == "ok"

    except Exception as e:
        health["error"] = str(e)

    return health
