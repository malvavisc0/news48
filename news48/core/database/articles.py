"""Article CRUD, search, stats, and query operations using SQLAlchemy ORM."""

import logging
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, text
from sqlalchemy.exc import IntegrityError

from .connection import SessionLocal, _hours_ago_iso, _utcnow
from .models import Article, Feed

# Constants from original connection.py
_VALID_PROCESSING_ACTIONS = {"download", "parse", "fact_check"}
_CLAIM_TIMEOUT_MINUTES = 30


def _claim_cutoff(minutes: int = _CLAIM_TIMEOUT_MINUTES) -> str:
    """Return the cutoff timestamp for stale processing claims."""
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()


def _strip_html_tags(text: str | None) -> str | None:
    """Remove any HTML tags from text."""
    if not text:
        return text
    return re.sub(r"<[^>]+>", "", text).strip()


def insert_articles(
    fetch_id: int,
    feed_id: int,
    entries: list[dict],
    source_name: str | None = None,
) -> int:
    """Batch insert articles from feed entries, ignoring duplicates by URL.

    Args:
        fetch_id: The current fetch ID.
        feed_id: The feed ID these articles belong to.
        entries: List of dicts with keys: url, title, summary, author,
            published_at, image_url.
        source_name: Optional denormalized feed/source name.

    Returns:
        Number of new articles inserted.
    """
    now = _utcnow()
    count = 0
    _log = logging.getLogger(__name__)
    skipped_no_url = 0
    duplicates = 0

    with SessionLocal() as session:
        for entry in entries:
            if not entry.get("url"):
                skipped_no_url += 1
                continue
            try:
                with session.begin_nested():
                    article = Article(
                        fetch_id=fetch_id,
                        feed_id=feed_id,
                        url=entry["url"],
                        title=_strip_html_tags(entry.get("title")),
                        summary=_strip_html_tags(entry.get("summary")),
                        author=entry.get("author"),
                        published_at=entry.get("published_at"),
                        created_at=now,
                        source_name=source_name or entry.get("source_name"),
                        image_url=entry.get("image_url"),
                    )
                    session.add(article)
                    session.flush()
                count += 1
            except IntegrityError:
                duplicates += 1

        if entries:
            _log.info(
                "insert_articles: %d entries, %d new, " "%d duplicates, %d no-url",
                len(entries),
                count,
                duplicates,
                skipped_no_url,
            )
        session.commit()

    return count


def update_article(
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
    """Update an article with parsed content from the parser agent."""
    summary = _strip_html_tags(summary)
    title = _strip_html_tags(title)
    content = _strip_html_tags(content) or ""

    if sentiment:
        sentiment = sentiment.lower()
    if categories:
        categories = categories.lower()
    if tags:
        tags = tags.lower()
    if countries:
        countries = countries.lower()

    with SessionLocal() as session:
        article = session.get(Article, article_id)
        if article:
            article.content = content
            if author:
                article.author = author
            if published_at:
                article.published_at = published_at
            if sentiment:
                article.sentiment = sentiment
            if categories:
                article.categories = categories
            if tags:
                article.tags = tags
            if summary:
                article.summary = summary
            if parsed_at:
                article.parsed_at = parsed_at
            if countries:
                article.countries = countries
            if title:
                article.title = title
            if image_url:
                article.image_url = image_url
            if language:
                article.language = language
            session.commit()


def update_article_fact_check(
    article_id: int,
    status: str,
    result: str | None = None,
    force: bool = False,
) -> bool:
    """Update the fact-check fields of an article."""
    valid_statuses = {"verified", "disputed", "unverifiable", "mixed"}
    if status.lower() not in valid_statuses:
        raise ValueError(
            f"Invalid fact_check_status '{status}'. "
            f"Valid: {', '.join(sorted(valid_statuses))}"
        )
    now = _utcnow()
    with SessionLocal() as session:
        article = session.get(Article, article_id)
        if article and (force or article.fact_check_status is None):
            article.fact_check_status = status.lower()
            article.fact_check_result = result
            article.fact_checked_at = now
            session.commit()
            return True
        return False


def claim_articles_for_processing(
    article_ids: list[int],
    action: str,
    owner: str,
    *,
    force: bool = False,
    stale_after_minutes: int = _CLAIM_TIMEOUT_MINUTES,
) -> list[int]:
    """Claim articles for a processing action."""
    if not article_ids:
        return []
    if action not in _VALID_PROCESSING_ACTIONS:
        raise ValueError(
            f"Invalid processing action '{action}'. "
            f"Valid: {', '.join(sorted(_VALID_PROCESSING_ACTIONS))}"
        )

    now = _utcnow()
    cutoff = _claim_cutoff(stale_after_minutes)

    with SessionLocal() as session:
        query = session.query(Article).filter(Article.id.in_(article_ids))
        if not force:
            query = query.filter(
                or_(
                    Article.processing_status.is_(None),
                    Article.processing_started_at.is_(None),
                    Article.processing_started_at < cutoff,
                    Article.processing_owner == owner,
                )
            )

        articles = query.with_for_update().all()
        for article in articles:
            article.processing_status = action
            article.processing_owner = owner
            article.processing_started_at = now
        session.commit()

        # Re-query to get the actually claimed IDs
        claimed = (
            session.query(Article.id)
            .filter(
                Article.id.in_(article_ids),
                Article.processing_status == action,
                Article.processing_owner == owner,
            )
            .all()
        )
        return [int(row[0]) for row in claimed]


def clear_article_processing_claim(
    article_id: int,
    owner: str | None = None,
) -> None:
    """Clear the processing claim for an article."""
    with SessionLocal() as session:
        article = session.get(Article, article_id)
        if article:
            if owner is None or article.processing_owner == owner:
                article.processing_status = None
                article.processing_owner = None
                article.processing_started_at = None
                session.commit()


def get_unparsed_articles(
    limit: int = 50, feed_domain: str | None = None
) -> list[dict]:
    """Get articles that have not been parsed yet."""
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
            .limit(limit)
        )
        if feed_domain:
            query = query.filter(Feed.url.like(f"%{feed_domain}%"))

        rows = query.all()
        return [
            {**article.to_dict(), "feed_url": feed_url} for article, feed_url in rows
        ]


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
            query = query.filter(Feed.url.like(f"%{feed_domain}%"))

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
            query = query.filter(Feed.url.like(f"%{feed_domain}%"))

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
            query = query.filter(Feed.url.like(f"%{feed_domain}%"))

        rows = query.all()
        return [
            {**article.to_dict(), "feed_url": feed_url} for article, feed_url in rows
        ]


def reset_article_download(article_id: int) -> None:
    """Reset download_failed flag and clear download_error for an article."""
    with SessionLocal() as session:
        article = session.get(Article, article_id)
        if article:
            article.download_failed = False
            article.download_error = None
            session.commit()


def get_articles_paginated(
    limit: int = 20,
    offset: int = 0,
    feed_domain: str | None = None,
    status: str | None = None,
    language: str | None = None,
    category: str | None = None,
    sentiment: str | None = None,
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
            "articles.parsed_at IS NOT NULL " "AND articles.fact_check_status IS NULL"
        ),
    }

    where_clauses = []
    params: dict = {}

    if feed_domain:
        where_clauses.append("feeds.url LIKE :feed_domain")
        params["feed_domain"] = f"%{feed_domain}%"

    if status and status in status_conditions:
        where_clauses.append(status_conditions[status])

    if language:
        where_clauses.append("articles.language = :language")
        params["language"] = language

    if category:
        where_clauses.append("articles.categories LIKE :category")
        params["category"] = f"%{category}%"

    if sentiment:
        where_clauses.append("articles.sentiment = :sentiment")
        params["sentiment"] = sentiment

    if hours is not None:
        where_clauses.append("articles.created_at >= :hours_ago")
        params["hours_ago"] = _hours_ago_iso(hours)

    if parsed:
        where_clauses.append("articles.parsed_at IS NOT NULL")

    where_sql = ""
    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)

    with SessionLocal() as session:
        # Get total count
        count_sql = (
            f"SELECT COUNT(*) FROM articles "
            f"JOIN feeds ON articles.feed_id = feeds.id {where_sql}"
        )
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

        # Get paginated results
        results_sql = (
            f"SELECT {select_cols} FROM articles "
            f"JOIN feeds ON articles.feed_id = feeds.id "
            f"{where_sql} "
            f"ORDER BY articles.created_at DESC "
            f"LIMIT :limit OFFSET :offset"
        )
        query_params = {**params, "limit": limit, "offset": offset}
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


def mark_article_download_failed(article_id: int, error: str) -> None:
    """Mark an article as having a failed download."""
    with SessionLocal() as session:
        article = session.get(Article, article_id)
        if article:
            article.download_failed = True
            article.download_error = error
            session.commit()


def mark_article_parse_failed(article_id: int, error: str) -> None:
    """Mark an article as having a failed parse."""
    with SessionLocal() as session:
        article = session.get(Article, article_id)
        if article and article.parse_failed is False:
            article.parse_failed = True
            article.parse_error = error
            session.commit()


def reset_article_parse(article_id: int) -> None:
    """Reset parse_failed flag and clear parse_error for an article."""
    with SessionLocal() as session:
        article = session.get(Article, article_id)
        if article:
            article.parse_failed = False
            article.parse_error = None
            article.parsed_at = None
            session.commit()


def delete_article(article_id: int) -> bool:
    """Delete an article by ID."""
    with SessionLocal() as session:
        article = session.get(Article, article_id)
        if article:
            session.delete(article)
            session.commit()
            return True
        return False


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
                    THEN 1 ELSE 0 END) AS malformed
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


def search_articles(
    query: str,
    limit: int = 20,
    offset: int = 0,
    hours: int = 48,
    sentiment: str | None = None,
    category: str | None = None,
) -> tuple[list[dict], int]:
    """Full-text search articles with optional filters."""
    where_clauses = ["a.created_at >= :hours_ago"]
    params: dict = {"hours_ago": _hours_ago_iso(hours)}

    if sentiment:
        where_clauses.append("a.sentiment = :sentiment")
        params["sentiment"] = sentiment

    if category:
        where_clauses.append("a.categories LIKE :category")
        params["category"] = f"%{category}%"

    where_sql = " AND ".join(where_clauses)

    with SessionLocal() as session:
        # Count total matches
        count = session.execute(
            text(
                f"SELECT COUNT(*) FROM articles a "
                f"WHERE MATCH(a.title, a.summary, a.content, a.tags, "
                f"a.categories) AGAINST(:query IN BOOLEAN MODE) "
                f"AND {where_sql}"
            ),
            {"query": query, **params},
        ).scalar()

        # Get paginated results
        rows = session.execute(
            text(
                f"SELECT a.*, f.title as source_name, "
                f"f.icon_url as feed_icon_url, "
                f"f.favicon_url as feed_favicon_url, "
                f"MATCH(a.title, a.summary, a.content, a.tags, a.categories) "
                f"AGAINST(:query IN BOOLEAN MODE) as rank "
                f"FROM articles a "
                f"JOIN feeds f ON a.feed_id = f.id "
                f"WHERE MATCH(a.title, a.summary, a.content, a.tags, "
                f"a.categories) AGAINST(:query IN BOOLEAN MODE) "
                f"AND {where_sql} "
                f"ORDER BY rank DESC "
                f"LIMIT :limit OFFSET :offset"
            ),
            {"query": query, **params, "limit": limit, "offset": offset},
        ).fetchall()

        return [dict(row._mapping) for row in rows], count or 0


def set_article_featured(article_id: int, featured: bool = True) -> None:
    """Mark/unmark an article as featured."""
    with SessionLocal() as session:
        article = session.get(Article, article_id)
        if article:
            article.is_featured = featured
            session.commit()


def set_article_breaking(article_id: int, breaking: bool = True) -> None:
    """Mark/unmark an article as breaking news."""
    with SessionLocal() as session:
        article = session.get(Article, article_id)
        if article:
            article.is_breaking = breaking
            session.commit()


def increment_view_count(article_id: int) -> None:
    """Atomically increment the view count for an article."""
    with SessionLocal() as session:
        session.execute(
            text("UPDATE articles SET view_count = view_count + 1 " "WHERE id = :id"),
            {"id": article_id},
        )
        session.commit()


def get_all_categories(hours: int = 48, parsed: bool = False) -> list[dict]:
    """Get distinct categories with article counts within time window."""
    threshold = _hours_ago_iso(hours)
    parsed_filter = "AND parsed_at IS NOT NULL" if parsed else ""

    with SessionLocal() as session:
        rows = session.execute(
            text(f"""
            SELECT categories FROM articles
            WHERE created_at >= :threshold AND categories IS NOT NULL
              AND categories != ''
              {parsed_filter}
        """),
            {"threshold": threshold},
        ).fetchall()

        counts: dict[str, int] = {}
        for row in rows:
            cats = row[0]
            if cats:
                for cat in cats.split(","):
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


def get_topic_clusters(
    hours: int = 48,
    limit: int = 8,
    min_articles: int = 3,
    per_cluster_limit: int = 3,
    excluded_tags: set[str] | None = None,
    parsed: bool = False,
) -> list[dict]:
    """Build lightweight topic clusters from recent article tags."""
    threshold = _hours_ago_iso(hours)
    ignored = {
        "news",
        "breaking",
        "update",
        "updates",
        "world",
        "latest",
        "story",
        "stories",
    }
    if excluded_tags:
        ignored.update(tag.strip().lower() for tag in excluded_tags if tag.strip())

    parsed_filter = "AND a.parsed_at IS NOT NULL" if parsed else ""

    with SessionLocal() as session:
        rows = session.execute(
            text(f"""
            SELECT a.id, a.title, a.summary, a.url,
                   a.published_at, a.created_at,
                   a.source_name, a.fact_check_status, a.tags,
                   f.title as feed_source_name
            FROM articles a
            JOIN feeds f ON a.feed_id = f.id
            WHERE a.created_at >= :threshold
              AND a.tags IS NOT NULL
              AND a.tags != ''
              {parsed_filter}
            ORDER BY a.created_at DESC
        """),
            {"threshold": threshold},
        ).fetchall()

    clusters: dict[str, dict] = {}
    for row in rows:
        row_dict = dict(row._mapping)
        tokens = []
        for raw_tag in (row_dict.get("tags") or "").split(","):
            tag = raw_tag.strip().lower()
            if not tag or tag in ignored or len(tag) < 3:
                continue
            tokens.append(tag)

        for tag in tokens:
            cluster = clusters.setdefault(
                tag,
                {
                    "name": tag,
                    "slug": tag.replace(" ", "-"),
                    "article_count": 0,
                    "articles": [],
                    "article_ids": set(),
                },
            )
            article_id = row_dict["id"]
            if article_id in cluster["article_ids"]:
                continue

            cluster["article_ids"].add(article_id)
            cluster["article_count"] += 1
            if len(cluster["articles"]) < per_cluster_limit:
                cluster["articles"].append(
                    {
                        "id": article_id,
                        "title": row_dict.get("title"),
                        "summary": row_dict.get("summary"),
                        "url": row_dict.get("url"),
                        "published_at": row_dict.get("published_at"),
                        "created_at": row_dict.get("created_at"),
                        "source_name": row_dict.get("source_name")
                        or row_dict.get("feed_source_name"),
                        "fact_check_status": row_dict.get("fact_check_status"),
                    }
                )

    ranked = sorted(
        (
            {
                "name": cluster["name"],
                "slug": cluster["slug"],
                "article_count": cluster["article_count"],
                "articles": cluster["articles"],
            }
            for cluster in clusters.values()
            if cluster["article_count"] >= min_articles
        ),
        key=lambda cluster: (-cluster["article_count"], cluster["name"]),
    )
    return ranked[:limit]


def get_articles_by_category(
    category: str,
    hours: int = 48,
    limit: int | None = 20,
    offset: int = 0,
    parsed: bool = False,
) -> tuple[list[dict], int]:
    """Get articles matching a category within the time window."""
    threshold = _hours_ago_iso(hours)
    parsed_filter = "AND a.parsed_at IS NOT NULL" if parsed else ""
    limit_clause = "LIMIT :limit OFFSET :offset" if limit is not None else ""

    with SessionLocal() as session:
        total = session.execute(
            text(f"""
            SELECT COUNT(*) FROM articles a
            WHERE a.categories LIKE :category
              AND a.created_at >= :threshold
              {parsed_filter}
        """),
            {"category": f"%{category}%", "threshold": threshold},
        ).scalar()

        rows = session.execute(
            text(f"""
            SELECT a.*, f.title as source_name,
                   f.icon_url as feed_icon_url,
                   f.favicon_url as feed_favicon_url
            FROM articles a
            JOIN feeds f ON a.feed_id = f.id
            WHERE a.categories LIKE :category
              AND a.created_at >= :threshold
              {parsed_filter}
            ORDER BY a.created_at DESC
            {limit_clause}
        """),
            {
                "category": f"%{category}%",
                "threshold": threshold,
                **({"limit": limit, "offset": offset} if limit is not None else {}),
            },
        ).fetchall()

        return [dict(row._mapping) for row in rows], total or 0


def get_articles_by_tag(
    tag: str,
    hours: int = 48,
    limit: int | None = 20,
    offset: int = 0,
    parsed: bool = False,
) -> tuple[list[dict], int]:
    """Get articles with a specific tag within the time window."""
    threshold = _hours_ago_iso(hours)
    parsed_filter = "AND a.parsed_at IS NOT NULL" if parsed else ""
    limit_clause = "LIMIT :limit OFFSET :offset" if limit is not None else ""

    with SessionLocal() as session:
        total = session.execute(
            text(f"""
            SELECT COUNT(*) FROM articles a
            WHERE a.tags LIKE :tag
              AND a.created_at >= :threshold
              {parsed_filter}
        """),
            {"tag": f"%{tag}%", "threshold": threshold},
        ).scalar()

        rows = session.execute(
            text(f"""
            SELECT a.id, a.title, a.summary, a.url,
                   a.published_at, a.created_at,
                   a.source_name, a.fact_check_status, a.tags,
                   f.title as feed_source_name
            FROM articles a
            JOIN feeds f ON a.feed_id = f.id
            WHERE a.tags LIKE :tag
              AND a.created_at >= :threshold
              {parsed_filter}
            ORDER BY a.created_at DESC
            {limit_clause}
        """),
            {
                "tag": f"%{tag}%",
                "threshold": threshold,
                **({"limit": limit, "offset": offset} if limit is not None else {}),
            },
        ).fetchall()

        return [dict(row._mapping) for row in rows], total or 0


def get_related_articles(
    article_id: int,
    limit: int = 5,
    parsed: bool = False,
) -> list[dict]:
    """Get related articles based on shared categories/tags."""
    with SessionLocal() as session:
        article = session.get(Article, article_id)
        if not article:
            return []

        tokens: list[str] = []
        if article.categories:
            tokens.extend(
                t.strip().lower() for t in article.categories.split(",") if t.strip()
            )
        if article.tags:
            tokens.extend(
                t.strip().lower() for t in article.tags.split(",") if t.strip()
            )

        if not tokens:
            return []

        # Build OR conditions for each token
        conditions = []
        params: dict = {"article_id": article_id}
        for i, token in enumerate(tokens[:10]):
            conditions.append(
                f"(a.categories LIKE :token_{i} OR a.tags LIKE :token_{i})"
            )
            params[f"token_{i}"] = f"%{token}%"

        where_sql = " OR ".join(conditions)
        parsed_filter = "AND a.parsed_at IS NOT NULL" if parsed else ""

        rows = session.execute(
            text(f"""
            SELECT a.*, f.title as source_name,
                   f.icon_url as feed_icon_url,
                   f.favicon_url as feed_favicon_url
            FROM articles a
            JOIN feeds f ON a.feed_id = f.id
            WHERE a.id != :article_id AND ({where_sql})
              {parsed_filter}
            ORDER BY a.created_at DESC
            LIMIT :limit
        """),
            {**params, "limit": limit},
        ).fetchall()

        return [dict(row._mapping) for row in rows]


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


def release_stale_article_claims(
    stale_after_minutes: int = _CLAIM_TIMEOUT_MINUTES,
) -> dict:
    """Release processing claims for articles stuck after a crash."""
    cutoff = _claim_cutoff(stale_after_minutes)

    with SessionLocal() as session:
        stale_query = session.query(Article).filter(
            Article.processing_status.in_(_VALID_PROCESSING_ACTIONS),
            Article.processing_started_at.is_not(None),
            Article.processing_started_at < cutoff,
        )

        count = stale_query.count()

        stale_query.update(
            {
                Article.processing_status: None,
                Article.processing_owner: None,
                Article.processing_started_at: None,
            },
            synchronize_session=False,
        )
        session.commit()

    return {"released": count or 0}


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
                SUM(CASE WHEN fact_check_status = 'verified'
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


def get_expiring_articles(within_hours: int = 6, parsed: bool = False) -> list[dict]:
    """Get articles that will expire within the given number of hours."""
    outer = _hours_ago_iso(48)
    inner = _hours_ago_iso(48 - within_hours)
    parsed_filter = "AND a.parsed_at IS NOT NULL" if parsed else ""

    with SessionLocal() as session:
        rows = session.execute(
            text(f"""
            SELECT a.id, a.title, a.url, a.created_at, a.source_name,
                   f.title as feed_source_name
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
