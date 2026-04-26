"""Article browsing operations: search, categories, countries, tags, clusters."""

from sqlalchemy import text

from news48.core.helpers.security import escape_like

from ..connection import SessionLocal, _hours_ago_db, _hours_ago_iso
from ..models import Article
from ._constants import _normalize_category


def search_articles(
    query: str,
    limit: int = 20,
    offset: int = 0,
    hours: int = 48,
    sentiment: str | None = None,
    category: str | None = None,
    country: str | None = None,
) -> tuple[list[dict], int]:
    """Full-text search articles with optional filters."""
    where_clauses = ["a.created_at >= :hours_ago"]
    params: dict = {"hours_ago": _hours_ago_iso(hours)}

    if sentiment:
        where_clauses.append("a.sentiment = :sentiment")
        params["sentiment"] = sentiment

    if category:
        where_clauses.append("a.categories LIKE :category ESCAPE '|'")
        params["category"] = f"%{escape_like(category)}%"

    if country:
        where_clauses.append("a.countries LIKE :country ESCAPE '|'")
        params["country"] = f"%{escape_like(country.strip().lower())}%"

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
                f"AGAINST(:query IN BOOLEAN MODE) as match_rank "
                f"FROM articles a "
                f"JOIN feeds f ON a.feed_id = f.id "
                f"WHERE MATCH(a.title, a.summary, a.content, a.tags, "
                f"a.categories) AGAINST(:query IN BOOLEAN MODE) "
                f"AND {where_sql} "
                f"ORDER BY match_rank DESC "
                f"LIMIT :limit OFFSET :offset"
            ),
            {"query": query, **params, "limit": limit, "offset": offset},
        ).fetchall()

        return [dict(row._mapping) for row in rows], count or 0


def get_all_countries(hours: int = 48, parsed: bool = False) -> list[dict]:
    """Get distinct countries with article counts within time window.

    Deduplicates by title so that the same story from multiple sources
    is only counted once per country.  Country codes are stored as
    comma-separated values (e.g. "us,gb,de").
    """
    threshold = _hours_ago_db(hours)

    with SessionLocal() as session:
        rows = session.execute(
            text(
                """
            SELECT a.countries FROM articles a
            INNER JOIN (
                SELECT MIN(id) as min_id FROM articles
                WHERE created_at >= :threshold
                  AND countries IS NOT NULL AND countries != ''
                  AND parsed_at IS NOT NULL
                GROUP BY title
            ) _dedup ON a.id = _dedup.min_id
        """
            ),
            {"threshold": threshold},
        ).fetchall()

        counts: dict[str, int] = {}
        for row in rows:
            raw = row[0]
            if raw:
                for code in raw.split(","):
                    code = code.strip().lower()
                    if code:
                        counts[code] = counts.get(code, 0) + 1

        return [
            {
                "name": name,
                "article_count": count,
            }
            for name, count in sorted(counts.items(), key=lambda x: -x[1])
        ]


def get_all_categories(hours: int = 48, parsed: bool = False) -> list[dict]:
    """Get distinct categories with article counts within time window.

    Deduplicates by title so that the same story from multiple sources
    is only counted once per category.  Normalizes separators (hyphens,
    underscores) to spaces so that e.g. 'artificial-intelligence' and
    'artificial intelligence' are merged.
    """
    threshold = _hours_ago_db(hours)
    parsed_filter = "AND a.parsed_at IS NOT NULL" if parsed else ""

    with SessionLocal() as session:
        rows = session.execute(
            text(
                f"""
            SELECT a.categories FROM articles a
            INNER JOIN (
                SELECT MIN(id) as min_id FROM articles
                WHERE created_at >= :threshold
                  AND categories IS NOT NULL AND categories != ''
                  {"AND parsed_at IS NOT NULL" if parsed else ""}
                GROUP BY title
            ) _dedup ON a.id = _dedup.min_id
        """
            ),
            {"threshold": threshold},
        ).fetchall()

        counts: dict[str, int] = {}
        for row in rows:
            cats = row[0]
            if cats:
                for cat in cats.split(","):
                    cat = _normalize_category(cat)
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
    threshold = _hours_ago_db(hours)
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
        ignored.update(
            tag.strip().lower() for tag in excluded_tags if tag.strip()
        )

    parsed_filter = "AND a.parsed_at IS NOT NULL" if parsed else ""

    with SessionLocal() as session:
        rows = session.execute(
            text(
                f"""
            SELECT a.id, a.title, a.slug, a.summary, a.url,
                   a.published_at, a.created_at,
                   a.source_name, a.fact_check_status, a.tags,
                   f.title as feed_source_name
            FROM articles a
            JOIN feeds f ON a.feed_id = f.id
            WHERE a.created_at >= :threshold
              AND a.tags IS NOT NULL
              AND a.tags != ''
              {parsed_filter}
            ORDER BY a.parsed_at DESC
        """
            ),
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
    sentiment: str | None = None,
) -> tuple[list[dict], int]:
    """Get articles matching a category within the time window.

    Deduplicates by title so that the same story from multiple sources
    only appears once.  Normalizes separators so that e.g. the slug
    'artificial-intelligence' matches articles stored with
    'artificial intelligence'.
    """
    threshold = _hours_ago_db(hours)
    parsed_filter = "AND a.parsed_at IS NOT NULL" if parsed else ""
    sentiment_filter = "AND a.sentiment = :sentiment" if sentiment else ""
    limit_clause = "LIMIT :limit OFFSET :offset" if limit is not None else ""

    # Normalize the incoming slug: hyphens -> spaces so LIKE works
    # against both "artificial-intelligence" and "artificial intelligence"
    norm_cat = _normalize_category(category)

    # Normalize stored categories on-the-fly for the comparison
    cat_condition = (
        "REPLACE(REPLACE(a.categories, '-', ' '), '_', ' ') "
        "LIKE :category ESCAPE '|'"
    )

    dedup_where = f"""
        WHERE {cat_condition}
          AND a.created_at >= :threshold
          {parsed_filter}
          {sentiment_filter}
    """
    dedup_sub = f"""
        SELECT MIN(a.id) as min_id
        FROM articles a
        {dedup_where}
        GROUP BY a.title
    """

    with SessionLocal() as session:
        params: dict = {
            "category": f"%{escape_like(norm_cat)}%",
            "threshold": threshold,
        }
        if sentiment:
            params["sentiment"] = sentiment

        total = session.execute(
            text(f"SELECT COUNT(*) FROM ({dedup_sub}) _dedup"),
            params,
        ).scalar()

        query_params = {
            **params,
            **(
                {"limit": limit, "offset": offset} if limit is not None else {}
            ),
        }
        rows = session.execute(
            text(
                f"""
            SELECT a.*, f.title as source_name,
                   f.icon_url as feed_icon_url,
                   f.favicon_url as feed_favicon_url
            FROM articles a
            JOIN feeds f ON a.feed_id = f.id
            INNER JOIN ({dedup_sub}) _dedup ON a.id = _dedup.min_id
            ORDER BY a.parsed_at DESC
            {limit_clause}
        """
            ),
            query_params,
        ).fetchall()

        return [dict(row._mapping) for row in rows], total or 0


def get_articles_by_tag(
    tag: str,
    hours: int = 48,
    limit: int | None = 20,
    offset: int = 0,
    parsed: bool = False,
) -> tuple[list[dict], int]:
    """Get articles with a specific tag within the time window.

    Deduplicates by title so that the same story from multiple
    sources only appears once.
    """
    threshold = _hours_ago_db(hours)
    parsed_filter = "AND a.parsed_at IS NOT NULL" if parsed else ""
    limit_clause = "LIMIT :limit OFFSET :offset" if limit is not None else ""

    dedup_sub = f"""
        SELECT MIN(a.id) as min_id
        FROM articles a
        WHERE a.tags LIKE :tag ESCAPE '|'
          AND a.created_at >= :threshold
          {parsed_filter}
        GROUP BY a.title
    """

    with SessionLocal() as session:
        params = {
            "tag": f"%{escape_like(tag)}%",
            "threshold": threshold,
        }

        total = session.execute(
            text(f"SELECT COUNT(*) FROM ({dedup_sub}) _dedup"),
            params,
        ).scalar()

        query_params = {
            **params,
            **(
                {"limit": limit, "offset": offset} if limit is not None else {}
            ),
        }
        rows = session.execute(
            text(
                f"""
            SELECT a.id, a.title, a.slug, a.summary, a.url,
                   a.published_at, a.created_at,
                   a.source_name, a.fact_check_status, a.tags,
                   f.title as feed_source_name
            FROM articles a
            JOIN feeds f ON a.feed_id = f.id
            INNER JOIN ({dedup_sub}) _dedup ON a.id = _dedup.min_id
            ORDER BY a.parsed_at DESC
            {limit_clause}
        """
            ),
            query_params,
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
                t.strip().lower()
                for t in article.categories.split(",")
                if t.strip()
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
                f"(a.categories LIKE :token_{i}" f" OR a.tags LIKE :token_{i})"
            )
            params[f"token_{i}"] = f"%{escape_like(token)}%"

        where_sql = " OR ".join(conditions)
        parsed_filter = "AND a.parsed_at IS NOT NULL" if parsed else ""

        rows = session.execute(
            text(
                f"""
            SELECT a.*, f.title as source_name,
                   f.icon_url as feed_icon_url,
                   f.favicon_url as feed_favicon_url
            FROM articles a
            JOIN feeds f ON a.feed_id = f.id
            WHERE a.id != :article_id AND ({where_sql})
              {parsed_filter}
            ORDER BY a.parsed_at DESC
            LIMIT :limit
        """
            ),
            {**params, "limit": limit},
        ).fetchall()

        return [dict(row._mapping) for row in rows]
