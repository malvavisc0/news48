"""Local MCP server exposing news48 operations as tools.

This server runs via stdio transport and is intended for use with
AI assistants like Claude Desktop, Cursor, etc.
"""

import json
import logging

from mcp import types
from mcp.server import Server
from mcp.server.stdio import stdio_server

logger = logging.getLogger(__name__)

app = Server("news48")

TOOLS = [
    types.Tool(
        name="fetch_feeds",
        description="Fetch RSS/Atom feeds from the database.",
        inputSchema={
            "type": "object",
            "properties": {
                "feed_domain": {
                    "type": "string",
                    "description": "Optional domain filter for feeds.",
                },
            },
        },
    ),
    types.Tool(
        name="list_feeds",
        description="List all feeds in the database.",
        inputSchema={
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of feeds to return.",
                    "default": 50,
                },
            },
        },
    ),
    types.Tool(
        name="search_articles",
        description="Search articles by keyword.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query string.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results to return.",
                    "default": 10,
                },
            },
            "required": ["query"],
        },
    ),
    types.Tool(
        name="get_article_detail",
        description="Get full article details including claims and fact-check results.",
        inputSchema={
            "type": "object",
            "properties": {
                "article_id": {
                    "type": "integer",
                    "description": "The article ID.",
                },
            },
            "required": ["article_id"],
        },
    ),
    types.Tool(
        name="get_stats",
        description="Get system statistics (article counts, feed counts, fetch stats).",
        inputSchema={
            "type": "object",
            "properties": {},
        },
    ),
    types.Tool(
        name="parse_article",
        description="Parse a single article using the LLM parser agent.",
        inputSchema={
            "type": "object",
            "properties": {
                "article_id": {
                    "type": "integer",
                    "description": "The article ID to parse.",
                },
            },
            "required": ["article_id"],
        },
    ),
]


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    """Return the list of available tools."""
    return TOOLS


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """Handle tool calls."""
    try:
        if name == "fetch_feeds":
            return await _fetch_feeds(arguments)
        elif name == "list_feeds":
            return await _list_feeds(arguments)
        elif name == "search_articles":
            return await _search_articles(arguments)
        elif name == "get_article_detail":
            return await _get_article_detail(arguments)
        elif name == "get_stats":
            return await _get_stats(arguments)
        elif name == "parse_article":
            return await _parse_article(arguments)
        else:
            return [types.TextContent(type="text", text=f"Unknown tool: {name}")]
    except Exception:
        logger.exception("Tool %s failed", name)
        return [
            types.TextContent(
                type="text",
                text="An internal error occurred.",
            )
        ]


def _clamp_int(value, default: int, lo: int, hi: int) -> int:
    """Clamp an integer argument to [lo, hi] range."""
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return default


async def _fetch_feeds(args: dict) -> list[types.TextContent]:
    from news48.core.database import get_all_feeds

    feeds = get_all_feeds()
    domain = args.get("feed_domain")
    if domain:
        feeds = [f for f in feeds if domain in f.get("url", "")]
    return [
        types.TextContent(type="text", text=json.dumps(feeds, default=str, indent=2))
    ]


async def _list_feeds(args: dict) -> list[types.TextContent]:
    from news48.core.database import get_all_feeds

    limit = _clamp_int(args.get("limit"), 50, 1, 200)
    feeds = get_all_feeds()[:limit]
    return [
        types.TextContent(type="text", text=json.dumps(feeds, default=str, indent=2))
    ]


async def _search_articles(args: dict) -> list[types.TextContent]:
    from news48.core.database import search_articles

    query = args.get("query", "")
    if not query:
        return [types.TextContent(type="text", text="query is required")]
    limit = _clamp_int(args.get("limit"), 10, 1, 100)
    results = search_articles(query, limit=limit)
    return [
        types.TextContent(type="text", text=json.dumps(results, default=str, indent=2))
    ]


async def _get_article_detail(args: dict) -> list[types.TextContent]:
    from news48.core.database import get_article_by_id, get_claims_for_article

    article_id = _clamp_int(args.get("article_id"), 0, 1, 999999999)
    if article_id == 0:
        return [types.TextContent(type="text", text="Invalid article_id")]
    article = get_article_by_id(article_id)
    if not article:
        return [types.TextContent(type="text", text=f"Article {article_id} not found")]
    claims = get_claims_for_article(article_id)
    result = {
        "article": article if isinstance(article, dict) else article.to_dict(),
        "claims": claims,
    }
    return [
        types.TextContent(type="text", text=json.dumps(result, default=str, indent=2))
    ]


async def _get_stats(args: dict) -> list[types.TextContent]:
    from news48.core.database import get_article_stats, get_feed_stats, get_fetch_stats

    stats = {
        "articles": get_article_stats(),
        "feeds": get_feed_stats(),
        "fetches": get_fetch_stats(),
    }
    return [
        types.TextContent(type="text", text=json.dumps(stats, default=str, indent=2))
    ]


async def _parse_article(args: dict) -> list[types.TextContent]:
    from news48.core.agents import run_parser

    article_id = _clamp_int(args.get("article_id"), 0, 1, 999999999)
    if article_id == 0:
        return [types.TextContent(type="text", text="Invalid article_id")]
    result = await run_parser(article_id)
    return [
        types.TextContent(type="text", text=json.dumps(result, default=str, indent=2))
    ]


async def main():
    """Run the MCP server via stdio transport."""
    async with stdio_server() as streams:
        await app.run(streams[0], streams[1], app.create_initialization_options())
