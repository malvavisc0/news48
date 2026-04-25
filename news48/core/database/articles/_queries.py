"""Article query operations: lookups, listing, and filtered retrieval."""

from itertools import zip_longest

from sqlalchemy import text

from news48.core.helpers.security import escape_like

from ..connection import SessionLocal, _hours_ago_iso
from ..models import Article, Feed
from ._constants import _normalize_category


def get_unparsed_articles(
    limit: int = 50, feed_domain: str | None = None
) -> list[dict]:
    """Get unparsed articles, round-robin across sources for diversity.

    Fetches a larger pool and interleaves across feeds so that
    articles from many sources are represented in each batch.
    """
    # Fetch a larger pool to have enough candidates for interleaving
    fetch_limit = limit * 3
    with SessionLocal() as session:
        query = (
            session.query(Article, Feed.url.label("feed_url"))
            .join(Feed, Article.feed_id == Feed.id)
            .filter(
                Article.content.isnot(None),
                Article.content != "",
                Article.parsed_at.is_(None),
                Article.parse_failed.is_(False),
            )
            .order_by(Article.created_at.asc())
            .limit(fetch_limit)
        )
        if feed_domain:
            query = query.filter(Feed.url.like(f"%{escape_like(feed_domain)}%"))

        rows = query.all()

        # Group articles by feed_id, preserving created_at order
        by_feed: dict[int, list[dict]] = {}
        for article, feed_url in rows:
            by_feed.setdefault(article.feed_id, []).append(
                {**article.to_dict(), "feed_url": feed_url}
            )

        # Round-robin: take one from each feed in turn
        result: list[dict] = []
        feed_iters = [iter(articles) for articles in by_feed.values()]
        for items in zip_longest(*feed_iters):
            for item in items:
                if item is not None:
                    result.append(item)
                    if len(result) >= limit:
                        return result

        return result


def get_parse_failed_articles(
    limit: int = 50, feed_domain: str | None = None
) -> list[dict]:
    """Get articles that have failed parsing."""
    with SessionLocal() as session:
        query = (
            session.query(Article, Feed.url.label("feed_url"))
            .join(Feed, Article.feed_id == Feed.id)
            .filter(Article.parse_failed.is_(True))
            .order_by(Article.created_at.asc())
            .limit(limit)
        )
        if feed_domain:
            query = query.filter(Feed.url.like(f"%{escape_like(feed_domain)}%"))

        rows = query.all()
        return [
            {**article.to_dict(), "feed_url": feed_url} for article, feed_url in rows
        ]


def get_empty_articles(limit: int = 50, feed_domain: str | None = None) -> list[dict]:
    """Get articles that have no content."""
    with SessionLocal() as session:
        query = (
            session.query(Article, Feed.url.label("feed_url"))
            .join(Feed, Article.feed_id == Feed.id)
            .filter(
                Article.content.is_(None),
                Article.download_failed.is_(False),
            )
            .order_by(Article.created_at.asc())
            .limit(limit)
        )
        if feed_domain:
            query = query.filter(Feed.url.like(f"%{escape_like(feed_domain)}%"))

        rows = query.all()
        return [
            {**article.to_dict(), "feed_url": feed_url} for article, feed_url in rows
        ]


def get_download_failed_articles(
    limit: int = 50, feed_domain: str | None = None
) -> list[dict]:
    """Get articles where download_failed = 1."""
    with SessionLocal() as session:
        query = (
            session.query(Article, Feed.url.label("feed_url"))
            .join(Feed, Article.feed_id == Feed.id)
            .filter(Article.download_failed.is_(True))
            .order_by(Article.created_at.asc())
            .limit(limit)
        )
        if feed_domain:
            query = query.filter(Feed.url.like(f"%{escape_like(feed_domain)}%"))

        rows = query.all()
        return [
            {**article.to_dict(), "feed_url": feed_url} for article, feed_url in rows
        ]


def get_articles_paginated(
    limit: int | None = 20,
    offset: int = 0,
    feed_domain: str | None = None,
    status: str | None = None,
    language: str | None = None,
    category: str | None = None,
    sentiment: str | None = None,
    country: str | None = None,
    hours: int | None = None,
    include_source: bool = False,
    parsed: bool = False,
) -> tuple[list[dict], int]:
    """Return filtered, paginated articles and total count."""
    status_conditions = {
        "empty": "articles.content IS NULL AND articles.download_failed = 0",
        "downloaded": (
            "articles.content IS NOT NULL AND articles.parsed_at IS NULL "
            "AND articles.parse_failed = 0"
        ),
        "parsed": "articles.parsed_at IS NOT NULL",
        "download-failed": "articles.download_failed = 1",
        "parse-failed": "articles.parse_failed = 1",
        "fact-checked": "articles.fact_check_status IS NOT NULL",
        "fact-unchecked": (
            "articles.parsed_at IS NOT NULL AND articles.fact_check_status IS NULL"
        ),
        "fact-check-error": "articles.fact_check_status = 'fact_check_error'",
    }

    where_clauses = []
    params: dict = {}

    if feed_domain:
        where_clauses.append("feeds.url LIKE :feed_domain ESCAPE '|'")
        params["feed_domain"] = f"%{escape_like(feed_domain)}%"

    if status and status in status_conditions:
        where_clauses.append(status_conditions[status])

    if language:
        where_clauses.append("articles.language = :language")
        params["language"] = language

    if category:
        where_clauses.append(
            "REPLACE(REPLACE(articles.categories, '-', ' '), '_', ' ') "
            "LIKE :category ESCAPE '|'"
        )
        params["category"] = f"%{escape_like(_normalize_category(category))}%"

    if sentiment:
        where_clauses.append("articles.sentiment = :sentiment")
        params["sentiment"] = sentiment

    if country:
        where_clauses.append("articles.countries LIKE :country ESCAPE '|'")
        params["country"] = f"%{escape_like(country.strip().lower())}%"

    if hours is not None:
        where_clauses.append("articles.created_at >= :hours_ago")
        params["hours_ago"] = _hours_ago_iso(hours)

    if parsed:
        where_clauses.append("articles.parsed_at IS NOT NULL")

    where_sql = ""
    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)

    # Deduplicate by title: pick one article per unique title
    dedup_sub = (
        f"SELECT MIN(articles.id) as min_id "
        f"FROM articles "
        f"JOIN feeds ON articles.feed_id = feeds.id "
        f"{where_sql} "
        f"GROUP BY articles.title"
    )

    with SessionLocal() as session:
        # Get total count (deduplicated)
        count_sql = f"SELECT COUNT(*) FROM ({dedup_sub}) _dedup"
        total = session.execute(text(count_sql), params).scalar()

        # Build select columns
        if include_source:
            select_cols = (
                "articles.*, feeds.title as source_name, "
                "feeds.icon_url as feed_icon_url, "
                "feeds.favicon_url as feed_favicon_url"
            )
        else:
            select_cols = (
                "articles.id, articles.url, articles.title, "
                "feeds.url as feed_url, "
                "articles.content IS NOT NULL as has_content, "
                "articles.parsed_at IS NOT NULL as is_parsed, "
                "articles.download_failed, articles.parse_failed, "
                "articles.fact_check_status, "
                "articles.processing_status, "
                "articles.processing_owner, "
                "articles.processing_started_at, "
                "articles.created_at, articles.published_at"
            )

        # Get paginated results (deduplicated)
        limit_clause = "LIMIT :limit OFFSET :offset" if limit is not None else ""
        results_sql = (
            f"SELECT {select_cols} FROM articles "
            f"JOIN feeds ON articles.feed_id = feeds.id "
            f"INNER JOIN ({dedup_sub}) _dedup "
            f"ON articles.id = _dedup.min_id "
            f"ORDER BY articles.parsed_at DESC "
            f"{limit_clause}"
        )
        query_params = {**params, "offset": offset}
        if limit is not None:
            query_params["limit"] = limit
        rows = session.execute(text(results_sql), query_params).fetchall()

        result = []
        for row in rows:
            row_dict = dict(row._mapping)
            result.append(row_dict)

        return result, total


def get_article_by_id(article_id: int) -> dict | None:
    """Look up an article by its ID."""
    with SessionLocal() as session:
        article = session.get(Article, article_id)
        return article.to_dict() if article else None


def get_article_by_url(url: str) -> dict | None:
    """Look up an article by its URL."""
    with SessionLocal() as session:
        article = session.query(Article).filter(Article.url == url).first()
        return article.to_dict() if article else None


def get_articles_with_missing_fields(
    limit: int = 50,
) -> list[dict]:
    """Get parsed articles that are missing required fields.

    Returns articles where parsed_at is set but summary, categories,
    or sentiment are NULL or empty.
    """
    with SessionLocal() as session:
        rows = session.execute(
            text("""
            SELECT a.*, f.url as feed_url,
                   f.title as feed_source_name
            FROM articles a
            JOIN feeds f ON a.feed_id = f.id
            WHERE a.parsed_at IS NOT NULL
              AND (a.summary IS NULL OR a.summary = ''
                   OR a.categories IS NULL OR a.categories = ''
                   OR a.sentiment IS NULL OR a.sentiment = '')
            ORDER BY a.created_at DESC
            LIMIT :limit
        """),
            {"limit": limit},
        ).fetchall()

        result = []
        for row in rows:
            row_dict = dict(row._mapping)
            # Determine which fields are missing
            missing = []
            if not row_dict.get("summary"):
                missing.append("summary")
            if not row_dict.get("categories"):
                missing.append("categories")
            if not row_dict.get("sentiment"):
                missing.append("sentiment")
            if not row_dict.get("tags"):
                missing.append("tags")
            row_dict["missing"] = missing
            result.append(row_dict)

        return result


def get_article_detail(article_id: int, parsed: bool = False) -> dict | None:
    """Get full article detail for display page."""
    parsed_filter = "AND a.parsed_at IS NOT NULL" if parsed else ""

    with SessionLocal() as session:
        row = session.execute(
            text(f"""
            SELECT a.*, f.title as source_name,
                   f.url as feed_url,
                   f.icon_url as feed_icon_url,
                   f.favicon_url as feed_favicon_url
            FROM articles a
            JOIN feeds f ON a.feed_id = f.id
            WHERE a.id = :article_id
              {parsed_filter}
        """),
            {"article_id": article_id},
        ).fetchone()

        return dict(row._mapping) if row else None


def get_articles_older_than_hours(hours: int = 48) -> list[dict]:
    """Get articles older than specified hours."""
    with SessionLocal() as session:
        threshold = _hours_ago_iso(hours)
        rows = session.execute(
            text("""
            SELECT a.*, f.url as feed_url
            FROM articles a
            JOIN feeds f ON a.feed_id = f.id
            WHERE a.created_at < :threshold
            ORDER BY a.created_at ASC
        """),
            {"threshold": threshold},
        ).fetchall()

        return [dict(row._mapping) for row in rows]


def get_expiring_articles(within_hours: int = 6, parsed: bool = False) -> list[dict]:
    """Get articles that will expire within the given number of hours."""
    outer = _hours_ago_iso(48)
    inner = _hours_ago_iso(48 - within_hours)
    parsed_filter = "AND a.parsed_at IS NOT NULL" if parsed else ""

    with SessionLocal() as session:
        rows = session.execute(
            text(f"""
            SELECT a.id, a.title, a.slug, a.url, a.created_at,
                   a.source_name, f.title as feed_source_name
            FROM articles a
            JOIN feeds f ON a.feed_id = f.id
            WHERE a.created_at >= :outer AND a.created_at < :inner
              {parsed_filter}
            ORDER BY a.created_at ASC
            LIMIT 10
        """),
            {"outer": outer, "inner": inner},
        ).fetchall()

        return [dict(row._mapping) for row in rows]
