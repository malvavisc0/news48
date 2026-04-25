"""Shared MCP tool definitions, schemas, and execution logic.

Both the local (stdio) and remote (HTTP) MCP servers delegate here
for tool registration and execution. This ensures identical behavior
across both endpoints.
"""

import json
import logging
from typing import Any

from mcp import types

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

TOOLS: list[types.Tool] = [
    types.Tool(
        name="get_briefing",
        description=(
            "Get a structured news briefing: top stories, trending topics, "
            "and breaking news. This is the primary entry point for agents "
            "that need current event context."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "hours": {
                    "type": "integer",
                    "description": "Look back window in hours. Default: 48. Range: 1-168.",
                    "default": 48,
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of top stories. Default: 10. Range: 1-50.",
                    "default": 10,
                },
            },
        },
    ),
    types.Tool(
        name="search_news",
        description=(
            "Full-text search across news articles with optional filters. "
            "Powered by MySQL full-text index across title, summary, content, "
            "tags, and categories. Returns results ranked by relevance."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query. Supports boolean operators (AND, OR, quotes).",
                },
                "hours": {
                    "type": "integer",
                    "description": "Time window in hours. Default: 48. Range: 1-168.",
                    "default": 48,
                },
                "sentiment": {
                    "type": "string",
                    "description": "Filter by sentiment.",
                    "enum": ["positive", "negative", "neutral"],
                },
                "category": {
                    "type": "string",
                    "description": "Filter by category name or slug.",
                },
                "country": {
                    "type": "string",
                    "description": "Filter by country code (e.g., 'us', 'gb', 'de').",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results. Default: 10. Range: 1-50.",
                    "default": 10,
                },
            },
            "required": ["query"],
        },
    ),
    types.Tool(
        name="get_article",
        description=(
            "Get a full article with its fact-check claims and optionally "
            "related articles from other sources. This is the deep-dive tool "
            "-- call it after finding an article via search_news or get_briefing."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "article_id": {
                    "type": "integer",
                    "description": "The article ID (from search or briefing results).",
                },
                "include_related": {
                    "type": "boolean",
                    "description": "Include related articles from other sources. Default: true.",
                    "default": True,
                },
            },
            "required": ["article_id"],
        },
    ),
    types.Tool(
        name="browse_category",
        description=(
            "Browse articles within a specific category or tag. "
            "Complements search_news for exploring topic areas. "
            "Accepts category names or slugs."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Category name or slug (e.g., 'technology', 'artificial-intelligence').",
                },
                "hours": {
                    "type": "integer",
                    "description": "Time window in hours. Default: 48. Range: 1-168.",
                    "default": 48,
                },
                "sentiment": {
                    "type": "string",
                    "description": "Filter by sentiment.",
                    "enum": ["positive", "negative", "neutral"],
                },
                "country": {
                    "type": "string",
                    "description": "Filter by country code (e.g., 'us', 'gb', 'de').",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results. Default: 20. Range: 1-100.",
                    "default": 20,
                },
            },
            "required": ["category"],
        },
    ),
    types.Tool(
        name="list_categories",
        description=(
            "List all active news categories with article counts. "
            "Use it to discover available topics before calling browse_category."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "hours": {
                    "type": "integer",
                    "description": "Time window in hours. Default: 48. Range: 1-168.",
                    "default": 48,
                },
            },
        },
    ),
    types.Tool(
        name="list_countries",
        description=(
            "List all countries mentioned in recent articles with article "
            "counts. Use it to discover which countries are in the news, "
            "then filter search_news or browse_category by country."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "hours": {
                    "type": "integer",
                    "description": "Time window in hours. Default: 48. Range: 1-168.",
                    "default": 48,
                },
            },
        },
    ),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clamp_int(value: Any, default: int, lo: int, hi: int) -> int:
    """Clamp an integer argument to [lo, hi] range."""
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return default


def _text(data: Any) -> list[types.TextContent]:
    """Wrap a serializable object as a single TextContent response."""
    return [
        types.TextContent(type="text", text=json.dumps(data, default=str, indent=2))
    ]


def _error(message: str) -> list[types.TextContent]:
    """Wrap an error message as a TextContent response."""
    return [types.TextContent(type="text", text=json.dumps({"error": message}))]


def _compact_article(row: dict) -> dict:
    """Extract agent-relevant fields from a raw article row."""
    return {
        "id": row.get("id"),
        "title": row.get("title"),
        "summary": row.get("summary"),
        "url": row.get("url"),
        "source_name": (
            row.get("source_name")
            or row.get("feed_source_name")
            or row.get("source_name")
        ),
        "published_at": row.get("published_at"),
        "categories": row.get("categories"),
        "sentiment": row.get("sentiment"),
        "fact_check_status": row.get("fact_check_status"),
    }


def _full_article(row: dict) -> dict:
    """Extract full article fields for the get_article tool."""
    return {
        "id": row.get("id"),
        "title": row.get("title"),
        "summary": row.get("summary"),
        "content": row.get("content"),
        "url": row.get("url"),
        "source_name": (
            row.get("source_name")
            or row.get("feed_source_name")
            or row.get("source_name")
        ),
        "author": row.get("author"),
        "published_at": row.get("published_at"),
        "categories": row.get("categories"),
        "tags": row.get("tags"),
        "sentiment": row.get("sentiment"),
        "countries": row.get("countries"),
        "language": row.get("language"),
        "fact_check_status": row.get("fact_check_status"),
        "fact_check_result": row.get("fact_check_result"),
        "fact_checked_at": row.get("fact_checked_at"),
    }


# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------


async def execute_tool(
    name: str, arguments: dict, *, parsed_only: bool = False
) -> list[types.TextContent]:
    """Dispatch a tool call to the appropriate handler.

    Args:
        name: Tool name.
        arguments: Tool input arguments.
        parsed_only: If True, only return parsed articles (web endpoint).
    """
    try:
        if name == "get_briefing":
            return await _get_briefing(arguments, parsed_only=parsed_only)
        elif name == "search_news":
            return await _search_news(arguments, parsed_only=parsed_only)
        elif name == "get_article":
            return await _get_article(arguments, parsed_only=parsed_only)
        elif name == "browse_category":
            return await _browse_category(arguments, parsed_only=parsed_only)
        elif name == "list_categories":
            return await _list_categories(arguments, parsed_only=parsed_only)
        elif name == "list_countries":
            return await _list_countries(arguments, parsed_only=parsed_only)
        else:
            return _error(f"Unknown tool: {name}")
    except Exception:
        logger.exception("Tool %s failed", name)
        return _error("An internal error occurred.")


# ---------------------------------------------------------------------------
# Handler implementations
# ---------------------------------------------------------------------------


async def _get_briefing(
    args: dict, *, parsed_only: bool = False
) -> list[types.TextContent]:
    from sqlalchemy import text

    from news48.core.database.articles import (
        get_articles_paginated,
        get_topic_clusters,
        get_web_stats,
    )
    from news48.core.database.connection import SessionLocal

    hours = _clamp_int(args.get("hours"), 48, 1, 168)
    limit = _clamp_int(args.get("limit"), 10, 1, 50)

    # Top stories
    stories, _ = get_articles_paginated(
        hours=hours, limit=limit, include_source=True, parsed=parsed_only
    )
    top_stories = [_compact_article(s) for s in stories]

    # Trending topics (top 3 titles per cluster)
    clusters = get_topic_clusters(hours=hours, parsed=parsed_only)
    trending = []
    for c in clusters[:8]:
        trending.append(
            {
                "name": c["name"],
                "slug": c["slug"],
                "article_count": c["article_count"],
                "top_titles": [a["title"] for a in c.get("articles", [])[:3]],
            }
        )

    # Breaking news
    with SessionLocal() as session:
        rows = session.execute(text("""
                SELECT a.id, a.title, a.summary, a.published_at,
                       f.title as source_name
                FROM articles a
                JOIN feeds f ON a.feed_id = f.id
                WHERE a.is_breaking = 1
                  AND a.parsed_at IS NOT NULL
                ORDER BY a.created_at DESC
                LIMIT 5
            """)).fetchall()
    breaking = [
        {
            "id": r.id,
            "title": r.title,
            "summary": r.summary,
            "source_name": r.source_name,
            "published_at": r.published_at,
        }
        for r in rows
    ]

    # Stats
    stats_data = get_web_stats(hours=hours, parsed=parsed_only)
    stats = {
        "total_stories": stats_data.get("live_stories", 0),
        "sources": stats_data.get("sources", 0),
        "verified_count": stats_data.get("verified", 0),
        "hours_covered": hours,
    }

    return _text(
        {
            "top_stories": top_stories,
            "trending_topics": trending,
            "breaking": breaking,
            "stats": stats,
        }
    )


async def _search_news(
    args: dict, *, parsed_only: bool = False
) -> list[types.TextContent]:
    from news48.core.database.articles import search_articles

    query = args.get("query", "")
    if not query:
        return _error("query is required")

    hours = _clamp_int(args.get("hours"), 48, 1, 168)
    limit = _clamp_int(args.get("limit"), 10, 1, 50)
    sentiment = args.get("sentiment")
    category = args.get("category")

    country = args.get("country")

    articles, total = search_articles(
        query=query,
        limit=limit,
        hours=hours,
        sentiment=sentiment,
        category=category,
        country=country,
    )

    results = []
    for a in articles:
        entry = _compact_article(a)
        entry["rank"] = a.get("rank")
        results.append(entry)

    return _text(
        {
            "query": query,
            "total": total,
            "hours": hours,
            "articles": results,
        }
    )


async def _get_article(
    args: dict, *, parsed_only: bool = False
) -> list[types.TextContent]:
    from news48.core.database import get_article_by_id, get_claims_for_article
    from news48.core.database.articles import get_article_detail, get_related_articles

    article_id = _clamp_int(args.get("article_id"), 0, 1, 999999999)
    if article_id == 0:
        return _error("Invalid article_id")

    include_related = args.get("include_related", True)

    # Get full article detail (with source info join)
    article = get_article_detail(article_id, parsed=parsed_only)
    if not article:
        return _error(f"Article {article_id} not found")

    # Get claims
    claims = get_claims_for_article(article_id)

    result: dict[str, Any] = {
        "article": _full_article(article),
        "claims": [
            {
                "claim_text": c["claim_text"],
                "verdict": c["verdict"],
                "evidence_summary": c.get("evidence_summary"),
                "sources": c.get("sources", []),
            }
            for c in claims
        ],
    }

    # Optionally include related articles
    if include_related:
        related = get_related_articles(article_id, limit=3, parsed=parsed_only)
        result["related"] = [_compact_article(r) for r in related]

    return _text(result)


async def _browse_category(
    args: dict, *, parsed_only: bool = False
) -> list[types.TextContent]:
    from news48.core.database.articles import (
        get_articles_by_category,
        get_articles_by_tag,
    )

    category = args.get("category", "")
    if not category:
        return _error("category is required")

    hours = _clamp_int(args.get("hours"), 48, 1, 168)
    limit = _clamp_int(args.get("limit"), 20, 1, 100)
    sentiment = args.get("sentiment")

    # Try category first
    articles, total = get_articles_by_category(
        category,
        hours=hours,
        limit=limit,
        parsed=parsed_only,
        sentiment=sentiment,
    )

    # Fall back to tag matching if no results
    if not articles:
        articles, total = get_articles_by_tag(
            category, hours=hours, limit=limit, parsed=parsed_only
        )

    return _text(
        {
            "category": category,
            "total": total,
            "hours": hours,
            "articles": [_compact_article(a) for a in articles],
        }
    )


async def _list_categories(
    args: dict, *, parsed_only: bool = False
) -> list[types.TextContent]:
    from news48.core.database.articles import get_all_categories

    hours = _clamp_int(args.get("hours"), 48, 1, 168)
    categories = get_all_categories(hours=hours, parsed=parsed_only)

    return _text(
        {
            "hours": hours,
            "categories": categories,
        }
    )


async def _list_countries(
    args: dict, *, parsed_only: bool = False
) -> list[types.TextContent]:
    from news48.core.database.articles import get_all_countries

    hours = _clamp_int(args.get("hours"), 48, 1, 168)
    countries = get_all_countries(hours=hours, parsed=parsed_only)

    return _text(
        {
            "hours": hours,
            "countries": countries,
        }
    )
