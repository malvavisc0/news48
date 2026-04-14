"""Article CRUD, search, stats, and query operations."""

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from database.connection import (
    _CLAIM_TIMEOUT_MINUTES,
    _VALID_PROCESSING_ACTIONS,
    _claim_cutoff,
    _hours_ago_iso,
    _utcnow,
    get_connection,
)


def insert_articles(
    db_path: Path | None,
    fetch_id: int,
    feed_id: int,
    entries: list[dict],
    db: sqlite3.Connection | None = None,
    source_name: str | None = None,
) -> int:
    """Batch insert articles from feed entries, ignoring duplicates by URL.

    Args:
        db_path: Path to the SQLite database file.
            Required if db is not provided.
        fetch_id: The current fetch ID.
        feed_id: The feed ID these articles belong to.
        entries: List of dicts with keys: url, title, summary, author,
            published_at, image_url.
        db: Optional existing database connection. If provided, uses this
            connection instead of creating a new one. Caller is responsible
            for committing after all inserts.
        source_name: Optional denormalized feed/source name.

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
                        published_at, created_at, source_name, image_url)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        fetch_id,
                        feed_id,
                        entry["url"],
                        entry.get("title"),
                        entry.get("summary"),
                        entry.get("author"),
                        entry.get("published_at"),
                        now,
                        source_name or entry.get("source_name"),
                        entry.get("image_url"),
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
    image_url: str | None = None,
    language: str | None = None,
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
        image_url: Optionally update the primary image URL.
        language: Optionally update the ISO 639-1 language code.
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
                   title = COALESCE(?, title),
                   image_url = COALESCE(?, image_url),
                   language = COALESCE(?, language)
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
                image_url,
                language,
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
                     AND a.content != ''
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
                     AND a.content != ''
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
    language: str | None = None,
    category: str | None = None,
    sentiment: str | None = None,
    hours: int | None = None,
    include_source: bool = False,
) -> tuple[list[dict], int]:
    """Return filtered, paginated articles and total count.

    Args:
        db_path: Path to the SQLite database file.
        limit: Maximum number of articles to return.
        offset: Number of articles to skip.
        feed_domain: Optional domain to filter by feed URL.
        status: Optional status filter. One of: empty, downloaded,
            parsed, download-failed, parse-failed.
        language: Optional ISO 639-1 language code filter.
        category: Optional category filter (LIKE match).
        sentiment: Optional sentiment filter.
        hours: Optional time window filter in hours.
        include_source: If True, join feed data for source info.

    Returns:
        A tuple of (articles list, total count).
    """
    status_conditions = {
        "empty": "a.content IS NULL AND a.download_failed = 0",
        "downloaded": (
            "a.content IS NOT NULL AND a.parsed_at IS NULL " "AND a.parse_failed = 0"
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

    if language:
        where_clauses.append("a.language = ?")
        params.append(language)

    if category:
        where_clauses.append("a.categories LIKE '%' || ? || '%'")
        params.append(category)

    if sentiment:
        where_clauses.append("a.sentiment = ?")
        params.append(sentiment)

    if hours is not None:
        where_clauses.append("a.created_at >= ?")
        params.append(_hours_ago_iso(hours))

    where_sql = ""
    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)

    # Build select columns based on include_source
    if include_source:
        select_cols = (
            "a.*, f.title as source_name, "
            "f.icon_url as feed_icon_url, "
            "f.favicon_url as feed_favicon_url"
        )
    else:
        select_cols = (
            "a.id, a.url, a.title, f.url as feed_url, "
            "a.content IS NOT NULL as has_content, "
            "a.parsed_at IS NOT NULL as is_parsed, "
            "a.download_failed, a.parse_failed, "
            "a.fact_check_status, "
            "a.processing_status, "
            "a.processing_owner, "
            "a.processing_started_at, "
            "a.created_at, a.published_at"
        )

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
            f"""SELECT {select_cols}
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
        cursor = db.execute("SELECT * FROM articles WHERE id = ?", (article_id,))
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


def mark_article_download_failed(db_path: Path, article_id: int, error: str) -> None:
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


def mark_article_parse_failed(db_path: Path, article_id: int, error: str) -> None:
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
                SUM(CASE WHEN content IS NOT NULL AND content != ''
                    AND parsed_at IS NULL
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
        row["oldest_unparsed_at"] = oldest["oldest_unparsed_at"] if oldest else None

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
        cursor = db.execute("""SELECT f.title, f.url, COUNT(a.id) AS article_count
               FROM feeds f
               LEFT JOIN articles a ON f.id = a.feed_id
               GROUP BY f.id
               ORDER BY article_count DESC
               LIMIT 10""")
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


def search_articles(
    db_path: Path,
    query: str,
    limit: int = 20,
    offset: int = 0,
    hours: int = 48,
    sentiment: str | None = None,
    category: str | None = None,
) -> tuple[list[dict], int]:
    """Full-text search articles with optional filters.

    Returns (articles, total_count).
    """
    where_clauses = ["a.created_at >= ?"]
    params: list = [_hours_ago_iso(hours)]

    if sentiment:
        where_clauses.append("a.sentiment = ?")
        params.append(sentiment)

    if category:
        where_clauses.append("a.categories LIKE '%' || ? || '%'")
        params.append(category)

    where_sql = " AND ".join(where_clauses)

    with get_connection(db_path) as db:
        # Count total matches
        count_cursor = db.execute(
            f"""SELECT COUNT(*)
                FROM articles_fts fts
                JOIN articles a ON a.id = fts.rowid
                WHERE articles_fts MATCH ? AND {where_sql}""",
            [query, *params],
        )
        total = count_cursor.fetchone()[0]

        # Get paginated results with BM25 rank
        cursor = db.execute(
            f"""SELECT a.*, f.title as source_name,
                       f.icon_url as feed_icon_url,
                       f.favicon_url as feed_favicon_url,
                       bm25(articles_fts) as rank
                FROM articles_fts fts
                JOIN articles a ON a.id = fts.rowid
                JOIN feeds f ON a.feed_id = f.id
                WHERE articles_fts MATCH ? AND {where_sql}
                ORDER BY rank
                LIMIT ? OFFSET ?""",
            [query, *params, limit, offset],
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows], total


def set_article_featured(db_path: Path, article_id: int, featured: bool = True) -> None:
    """Mark/unmark an article as featured."""
    with get_connection(db_path) as db:
        db.execute(
            "UPDATE articles SET is_featured = ? WHERE id = ?",
            (int(featured), article_id),
        )
        db.commit()


def set_article_breaking(db_path: Path, article_id: int, breaking: bool = True) -> None:
    """Mark/unmark an article as breaking news."""
    with get_connection(db_path) as db:
        db.execute(
            "UPDATE articles SET is_breaking = ? WHERE id = ?",
            (int(breaking), article_id),
        )
        db.commit()


def get_featured_articles(db_path: Path, limit: int = 10) -> list[dict]:
    """Get all currently featured articles within 48h window."""
    threshold = _hours_ago_iso(48)
    with get_connection(db_path) as db:
        cursor = db.execute(
            """SELECT a.*, f.title as source_name,
                       f.icon_url as feed_icon_url,
                       f.favicon_url as feed_favicon_url
                FROM articles a
                JOIN feeds f ON a.feed_id = f.id
                WHERE a.is_featured = 1 AND a.created_at >= ?
                ORDER BY a.created_at DESC
                LIMIT ?""",
            (threshold, limit),
        )
        return [dict(row) for row in cursor.fetchall()]


def get_breaking_articles(db_path: Path, limit: int = 5) -> list[dict]:
    """Get all currently breaking news articles within 48h window."""
    threshold = _hours_ago_iso(48)
    with get_connection(db_path) as db:
        cursor = db.execute(
            """SELECT a.*, f.title as source_name,
                       f.icon_url as feed_icon_url,
                       f.favicon_url as feed_favicon_url
                FROM articles a
                JOIN feeds f ON a.feed_id = f.id
                WHERE a.is_breaking = 1 AND a.created_at >= ?
                ORDER BY a.created_at DESC
                LIMIT ?""",
            (threshold, limit),
        )
        return [dict(row) for row in cursor.fetchall()]


def increment_view_count(db_path: Path, article_id: int) -> None:
    """Atomically increment the view count for an article.

    Uses UPDATE ... SET view_count = view_count + 1 for atomicity.
    NOTE: The web API layer should implement rate limiting per
    IP/session to prevent abuse of this endpoint.
    """
    with get_connection(db_path) as db:
        db.execute(
            "UPDATE articles SET view_count = view_count + 1 " "WHERE id = ?",
            (article_id,),
        )
        db.commit()


def get_trending_articles(
    db_path: Path,
    hours: int = 24,
    limit: int = 10,
) -> list[dict]:
    """Get most-viewed articles within the given time window."""
    threshold = _hours_ago_iso(hours)
    with get_connection(db_path) as db:
        cursor = db.execute(
            """SELECT a.*, f.title as source_name,
                       f.icon_url as feed_icon_url,
                       f.favicon_url as feed_favicon_url
                FROM articles a
                JOIN feeds f ON a.feed_id = f.id
                WHERE a.created_at >= ?
                ORDER BY a.view_count DESC
                LIMIT ?""",
            (threshold, limit),
        )
        return [dict(row) for row in cursor.fetchall()]


def get_all_categories(db_path: Path, hours: int = 48) -> list[dict]:
    """Get distinct categories with article counts within time window.

    Parses the comma-separated categories column.
    Returns list of dicts: [{name, slug, article_count}]
    """
    threshold = _hours_ago_iso(hours)
    with get_connection(db_path) as db:
        cursor = db.execute(
            """SELECT categories FROM articles
                WHERE created_at >= ? AND categories IS NOT NULL
                  AND categories != ''""",
            (threshold,),
        )
        counts: dict[str, int] = {}
        for row in cursor.fetchall():
            for cat in row["categories"].split(","):
                cat = cat.strip().lower()
                if cat:
                    counts[cat] = counts.get(cat, 0) + 1
        return [
            {
                "name": name,
                "slug": name.replace(" ", "-"),
                "article_count": count,
            }
            for name, count in sorted(counts.items(), key=lambda x: -x[1])
        ]


def get_all_tags(db_path: Path, hours: int = 48, limit: int = 50) -> list[dict]:
    """Get most common tags with article counts within time window.

    Returns list of dicts: [{name, slug, article_count}]
    """
    threshold = _hours_ago_iso(hours)
    with get_connection(db_path) as db:
        cursor = db.execute(
            """SELECT tags FROM articles
                WHERE created_at >= ? AND tags IS NOT NULL
                  AND tags != ''""",
            (threshold,),
        )
        counts: dict[str, int] = {}
        for row in cursor.fetchall():
            for tag in row["tags"].split(","):
                tag = tag.strip().lower()
                if tag:
                    counts[tag] = counts.get(tag, 0) + 1
        return [
            {
                "name": name,
                "slug": name.replace(" ", "-"),
                "article_count": count,
            }
            for name, count in sorted(counts.items(), key=lambda x: -x[1])[:limit]
        ]


def get_articles_by_category(
    db_path: Path,
    category: str,
    hours: int = 48,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """Get articles matching a category within the time window.

    Uses LIKE matching on the comma-separated categories column.
    """
    threshold = _hours_ago_iso(hours)
    with get_connection(db_path) as db:
        count_cursor = db.execute(
            """SELECT COUNT(*) FROM articles
                WHERE categories LIKE '%' || ? || '%'
                  AND created_at >= ?""",
            (category, threshold),
        )
        total = count_cursor.fetchone()[0]

        cursor = db.execute(
            """SELECT a.*, f.title as source_name,
                       f.icon_url as feed_icon_url,
                       f.favicon_url as feed_favicon_url
                FROM articles a
                JOIN feeds f ON a.feed_id = f.id
                WHERE a.categories LIKE '%' || ? || '%'
                  AND a.created_at >= ?
                ORDER BY a.created_at DESC
                LIMIT ? OFFSET ?""",
            (category, threshold, limit, offset),
        )
        return [dict(row) for row in cursor.fetchall()], total


def get_articles_by_tag(
    db_path: Path,
    tag: str,
    hours: int = 48,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """Get articles with a specific tag within the time window."""
    threshold = _hours_ago_iso(hours)
    with get_connection(db_path) as db:
        count_cursor = db.execute(
            """SELECT COUNT(*) FROM articles
                WHERE tags LIKE '%' || ? || '%'
                  AND created_at >= ?""",
            (tag, threshold),
        )
        total = count_cursor.fetchone()[0]

        cursor = db.execute(
            """SELECT a.*, f.title as source_name,
                       f.icon_url as feed_icon_url,
                       f.favicon_url as feed_favicon_url
                FROM articles a
                JOIN feeds f ON a.feed_id = f.id
                WHERE a.tags LIKE '%' || ? || '%'
                  AND a.created_at >= ?
                ORDER BY a.created_at DESC
                LIMIT ? OFFSET ?""",
            (tag, threshold, limit, offset),
        )
        return [dict(row) for row in cursor.fetchall()], total


def get_related_articles(
    db_path: Path,
    article_id: int,
    limit: int = 5,
) -> list[dict]:
    """Get related articles based on shared categories/tags.

    Strategy: find articles that share the most category/tag tokens.
    """
    with get_connection(db_path) as db:
        # Get the article's categories and tags
        cursor = db.execute(
            "SELECT categories, tags FROM articles WHERE id = ?",
            (article_id,),
        )
        row = cursor.fetchone()
        if not row:
            return []

        tokens: list[str] = []
        if row["categories"]:
            tokens.extend(
                t.strip().lower() for t in row["categories"].split(",") if t.strip()
            )
        if row["tags"]:
            tokens.extend(
                t.strip().lower() for t in row["tags"].split(",") if t.strip()
            )

        if not tokens:
            return []

        # Build OR conditions for each token across categories and tags
        conditions = []
        params: list = []
        for token in tokens[:10]:  # Limit to avoid huge queries
            conditions.append(
                "(categories LIKE '%' || ? || '%' " "OR tags LIKE '%' || ? || '%')"
            )
            params.extend([token, token])

        where_sql = " OR ".join(conditions)
        cursor = db.execute(
            f"""SELECT a.*, f.title as source_name,
                       f.icon_url as feed_icon_url,
                       f.favicon_url as feed_favicon_url
                FROM articles a
                JOIN feeds f ON a.feed_id = f.id
                WHERE a.id != ? AND ({where_sql})
                ORDER BY a.created_at DESC
                LIMIT ?""",
            [article_id, *params, limit],
        )
        return [dict(row) for row in cursor.fetchall()]


def get_article_detail(db_path: Path, article_id: int) -> dict | None:
    """Get full article detail for display page.

    Includes all article fields and feed info via JOIN.
    """
    with get_connection(db_path) as db:
        cursor = db.execute(
            """SELECT a.*, f.title as source_name,
                       f.url as feed_url,
                       f.icon_url as feed_icon_url,
                       f.favicon_url as feed_favicon_url
                FROM articles a
                JOIN feeds f ON a.feed_id = f.id
                WHERE a.id = ?""",
            (article_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def get_articles_by_time_bucket(
    db_path: Path,
    bucket_hours: int = 6,
) -> list[dict]:
    """Get article counts grouped by time buckets.

    Returns list of dicts:
    - bucket_start, bucket_end, count
    Useful for timeline visualization on homepage.
    Buckets: last 0-6h, 6-12h, 12-18h, 18-24h, 24-36h, 36-48h
    """
    total_hours = 48
    num_buckets = total_hours // bucket_hours

    # Pre-compute bucket boundaries
    bucket_bounds = []
    for i in range(num_buckets):
        start_hours = i * bucket_hours
        end_hours = (i + 1) * bucket_hours
        bucket_bounds.append((_hours_ago_iso(end_hours), _hours_ago_iso(start_hours)))

    # Build a single query using CASE WHEN for all buckets
    case_parts = []
    params: list = []
    for idx, (start, end) in enumerate(bucket_bounds):
        case_parts.append(
            f"SUM(CASE WHEN created_at >= ? AND created_at < ? "
            f"THEN 1 ELSE 0 END) AS bucket_{idx}"
        )
        params.extend([start, end])

    sql = f"SELECT {', '.join(case_parts)} FROM articles"

    with get_connection(db_path) as db:
        cursor = db.execute(sql, params)
        row = cursor.fetchone()

    buckets = []
    for idx, (start, end) in enumerate(bucket_bounds):
        buckets.append(
            {
                "bucket_start": start,
                "bucket_end": end,
                "count": row[idx] or 0,
            }
        )

    return buckets


def get_articles_older_than_hours(db_path: Path, hours: int = 48) -> list[dict]:
    """Get articles older than specified hours.

    Args:
        db_path: Path to the SQLite database file.
        hours: Number of hours to use as threshold (default: 48).

    Returns:
        A list of dicts with article data for articles older than threshold.
    """
    with get_connection(db_path) as db:
        threshold = _hours_ago_iso(hours)

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


def release_stale_article_claims(
    db_path: Path,
    stale_after_minutes: int = _CLAIM_TIMEOUT_MINUTES,
) -> dict:
    """Release processing claims for articles stuck after a crash.

    Articles that were claimed for download or parsing but never
    completed (e.g. due to an orchestrator crash) will have their
    processing_status cleared so they can be re-claimed.

    Args:
        db_path: Path to the SQLite database file.
        stale_after_minutes: Minutes after which a claim is considered stale.

    Returns:
        A dict with ``released`` count of articles whose claims were cleared.
    """
    cutoff = _claim_cutoff(stale_after_minutes)

    with get_connection(db_path) as db:
        cursor = db.execute(
            """SELECT COUNT(*) FROM articles
               WHERE processing_status = 'claimed'
                 AND processing_started_at IS NOT NULL
                 AND processing_started_at < ?""",
            (cutoff,),
        )
        count = cursor.fetchone()[0]

        db.execute(
            """UPDATE articles
               SET processing_status = NULL,
                   processing_owner = NULL,
                   processing_started_at = NULL
               WHERE processing_status = 'claimed'
                 AND processing_started_at IS NOT NULL
                 AND processing_started_at < ?""",
            (cutoff,),
        )
        db.commit()

    return {"released": count}
