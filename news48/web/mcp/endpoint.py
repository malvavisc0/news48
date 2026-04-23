"""Remote MCP endpoint for the news48 web application.

Exposes read-only news browsing operations via MCP over Streamable HTTP.
Protected by API key authentication backed by Redis.
"""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from mcp import types
from mcp.server import Server
from mcp.server.streamable_http import StreamableHTTPServerTransport

from news48.web.mcp.auth import verify_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mcp", tags=["MCP"])
mcp_app = Server("news48-web")
security = HTTPBearer()

TOOLS = [
    types.Tool(
        name="browse_articles",
        description=("Browse recent articles with optional category filter."),
        inputSchema={
            "type": "object",
            "properties": {
                "hours": {
                    "type": "integer",
                    "description": "Look back N hours.",
                    "default": 48,
                },
                "category": {
                    "type": "string",
                    "description": "Optional category filter.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results.",
                    "default": 20,
                },
            },
        },
    ),
    types.Tool(
        name="get_topic_clusters",
        description="Get topic clusters for recent articles.",
        inputSchema={
            "type": "object",
            "properties": {
                "hours": {
                    "type": "integer",
                    "description": "Look back N hours.",
                    "default": 48,
                },
            },
        },
    ),
    types.Tool(
        name="article_detail",
        description="Get full article with fact-check claims.",
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
        name="web_stats",
        description="Get web-facing statistics.",
        inputSchema={
            "type": "object",
            "properties": {
                "hours": {
                    "type": "integer",
                    "description": "Look back N hours.",
                    "default": 48,
                },
            },
        },
    ),
]


async def _require_mcp_key(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    """FastAPI dependency that validates the MCP API key."""
    if not verify_key(credentials.credentials):
        raise HTTPException(
            status_code=401,
            detail="Invalid or revoked MCP API key",
        )
    return credentials.credentials


@mcp_app.list_tools()
async def list_tools() -> list[types.Tool]:
    """Return available web MCP tools."""
    return TOOLS


@mcp_app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """Handle tool calls for the web MCP endpoint."""
    try:
        if name == "browse_articles":
            return await _browse_articles(arguments)
        elif name == "get_topic_clusters":
            return await _get_topic_clusters(arguments)
        elif name == "article_detail":
            return await _article_detail(arguments)
        elif name == "web_stats":
            return await _web_stats(arguments)
        else:
            return [
                types.TextContent(type="text", text=f"Unknown tool: {name}")
            ]
    except Exception as e:
        logger.exception("Web MCP tool %s failed", name)
        return [types.TextContent(type="text", text=f"Error: {e}")]


async def _browse_articles(args: dict) -> list[types.TextContent]:
    from news48.core.database.articles import get_articles_paginated

    hours = args.get("hours", 48)
    category = args.get("category")
    limit = args.get("limit", 20)
    articles, _ = get_articles_paginated(
        limit=limit, hours=hours, category=category
    )
    return [
        types.TextContent(
            type="text",
            text=json.dumps(articles, default=str, indent=2),
        )
    ]


async def _get_topic_clusters(
    args: dict,
) -> list[types.TextContent]:
    from news48.core.database.articles import get_topic_clusters

    hours = args.get("hours", 48)
    clusters = get_topic_clusters(hours=hours)
    return [
        types.TextContent(
            type="text",
            text=json.dumps(clusters, default=str, indent=2),
        )
    ]


async def _article_detail(args: dict) -> list[types.TextContent]:
    from news48.core.database import get_article_by_id, get_claims_for_article

    article_id = args["article_id"]
    article = get_article_by_id(article_id)
    if not article:
        return [
            types.TextContent(
                type="text",
                text=f"Article {article_id} not found",
            )
        ]
    claims = get_claims_for_article(article_id)
    result = {
        "article": (
            article if isinstance(article, dict) else article.to_dict()
        ),
        "claims": claims,
    }
    return [
        types.TextContent(
            type="text",
            text=json.dumps(result, default=str, indent=2),
        )
    ]


async def _web_stats(args: dict) -> list[types.TextContent]:
    from news48.core.database.articles import get_web_stats

    hours = args.get("hours", 48)
    stats = get_web_stats(hours=hours)
    return [
        types.TextContent(
            type="text",
            text=json.dumps(stats, default=str, indent=2),
        )
    ]


@router.post("/", dependencies=[Depends(_require_mcp_key)])
async def mcp_endpoint(request: Request) -> Response:
    """Streamable HTTP endpoint for MCP connections.

    Bridges the ASGI request to the MCP StreamableHTTP transport.
    """
    transport = StreamableHTTPServerTransport(mcp_session_id=None)

    # Collect the response from the ASGI send callable
    response_body = b""
    response_status = 200
    response_headers: list[tuple[bytes, bytes]] = []

    async def send(message: dict) -> None:
        nonlocal response_body, response_status, response_headers
        if message["type"] == "http.response.start":
            response_status = message["status"]
            response_headers = message.get("headers", [])
        elif message["type"] == "http.response.body":
            response_body += message.get("body", b"")

    await transport.handle_request(request.scope, request.receive, send)

    return Response(
        content=response_body,
        status_code=response_status,
        headers=dict((k.decode(), v.decode()) for k, v in response_headers),
    )
