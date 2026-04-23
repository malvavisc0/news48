"""Remote MCP endpoint for the news48 web application.

Exposes read-only news browsing operations via MCP over Streamable HTTP.
Protected by API key authentication backed by Redis.

The ``MCPEndpoint`` class is an ASGI app that:
  1. Validates Bearer-token auth against Redis on every request.
  2. Delegates to ``StreamableHTTPServerTransport.handle_request``.

Lifecycle (``startup`` / ``shutdown``) is driven by the FastAPI app
lifespan in ``news48.web.app``.
"""

import asyncio
import json
import logging

from mcp import types
from mcp.server import Server
from mcp.server.streamable_http import StreamableHTTPServerTransport
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import Receive, Scope, Send

from news48.web.mcp.auth import verify_key

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# MCP Server + tool definitions
# ---------------------------------------------------------------------------

mcp_app = Server("news48-web")

TOOLS = [
    types.Tool(
        name="browse_articles",
        description="Browse recent articles with optional category filter.",
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
            return [types.TextContent(type="text", text=f"Unknown tool: {name}")]
    except Exception as e:
        logger.exception("Web MCP tool %s failed", name)
        return [types.TextContent(type="text", text=f"Error: {e}")]


# -- Tool implementations ---------------------------------------------------


async def _browse_articles(args: dict) -> list[types.TextContent]:
    from news48.core.database.articles import get_articles_paginated

    hours = args.get("hours", 48)
    category = args.get("category")
    limit = args.get("limit", 20)
    articles, _ = get_articles_paginated(limit=limit, hours=hours, category=category)
    return [
        types.TextContent(
            type="text",
            text=json.dumps(articles, default=str, indent=2),
        )
    ]


async def _get_topic_clusters(args: dict) -> list[types.TextContent]:
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
        "article": (article if isinstance(article, dict) else article.to_dict()),
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


# ---------------------------------------------------------------------------
# ASGI app: auth middleware + transport passthrough
# ---------------------------------------------------------------------------


class MCPEndpoint:
    """ASGI application that authenticates and delegates to MCP transport.

    The transport's ``handle_request`` is a native ASGI handler, so we
    pass ``scope/receive/send`` straight through after verifying the
    Bearer token.  This preserves streaming (SSE / chunked) semantics
    that would be lost by buffering the response.

    Call ``startup()`` before the first request and ``shutdown()`` when
    the application is stopping.
    """

    def __init__(self) -> None:
        self._transport: StreamableHTTPServerTransport | None = None
        self._server_task: asyncio.Task | None = None  # type: ignore[type-arg]
        self._connect_cm: object | None = None

    # -- lifecycle -----------------------------------------------------------

    async def startup(self) -> None:
        """Create transport, connect streams, start the MCP server loop."""
        self._transport = StreamableHTTPServerTransport(
            mcp_session_id=None,
        )
        self._connect_cm = self._transport.connect()
        # Enter the context manager manually so it stays open
        cm = self._connect_cm
        streams = await cm.__aenter__()  # type: ignore[union-attr]
        self._server_task = asyncio.create_task(
            mcp_app.run(
                streams[0],
                streams[1],
                mcp_app.create_initialization_options(),
            )
        )
        logger.info("MCP web endpoint started (Streamable HTTP)")

    async def shutdown(self) -> None:
        """Cancel the server task and close the transport connection."""
        if self._server_task is not None:
            self._server_task.cancel()
            try:
                await self._server_task
            except asyncio.CancelledError:
                pass
            self._server_task = None
        if self._connect_cm is not None:
            cm = self._connect_cm
            await cm.__aexit__(None, None, None)  # type: ignore[union-attr]
            self._connect_cm = None
        if self._transport is not None:
            self._transport = None
        logger.info("MCP web endpoint stopped")

    # -- ASGI handler --------------------------------------------------------

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI entry point — validate auth then delegate to transport."""
        if scope["type"] != "http":
            return

        # --- authenticate ---------------------------------------------------
        request = Request(scope)
        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            response = JSONResponse(
                {"detail": "Missing Bearer token"},
                status_code=401,
            )
            await response(scope, receive, send)
            return

        api_key = auth_header[7:]
        if not verify_key(api_key):
            response = JSONResponse(
                {"detail": "Invalid or revoked MCP API key"},
                status_code=401,
            )
            await response(scope, receive, send)
            return

        # --- delegate to transport ------------------------------------------
        if self._transport is None:
            response = JSONResponse(
                {"detail": "MCP endpoint not ready"},
                status_code=503,
            )
            await response(scope, receive, send)
            return

        await self._transport.handle_request(scope, receive, send)


# Module-level singleton — mounted by ``news48.web.app``.
mcp_endpoint = MCPEndpoint()
