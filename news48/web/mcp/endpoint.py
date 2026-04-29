"""Remote MCP endpoint for the news48 web application.

Exposes read-only news browsing operations via MCP over Streamable HTTP.
Protected by API key authentication backed by Redis.

The ``MCPEndpoint`` class is an ASGI app that:
  1. Validates Bearer-token auth against Redis on every request.
  2. Delegates to ``StreamableHTTPServerTransport.handle_request``.

All tool definitions and execution logic are in news48.mcp.tools,
shared with the local stdio server.  The web endpoint passes
``parsed_only=True`` so only fully parsed articles are returned.
"""

import asyncio
import logging

from mcp import types
from mcp.server import Server
from mcp.server.streamable_http import StreamableHTTPServerTransport
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import Receive, Scope, Send

from news48.mcp.tools import TOOLS, execute_tool
from news48.web.mcp.auth import verify_key

logger = logging.getLogger(__name__)

mcp_app = Server("news48")


@mcp_app.list_tools()
async def list_tools() -> list[types.Tool]:
    """Return available web MCP tools."""
    return TOOLS


@mcp_app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """Handle tool calls for the web MCP endpoint."""
    return await execute_tool(name, arguments, parsed_only=True)


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

    # -- CORS headers for direct responses ----------------------------------
    # The MCPEndpoint is reached via a middleware that bypasses the main
    # app's CORSMiddleware send-wrapper for responses it produces directly
    # (JSONResponse for auth / readiness errors).  We attach CORS headers
    # ourselves so browser-based MCP clients can read the error body.
    _CORS = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
        "Access-Control-Allow-Headers": "*",
    }

    # -- ASGI handler --------------------------------------------------------

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI entry point — validate auth then delegate to transport."""
        if scope["type"] != "http":
            return

        # --- CORS preflight -------------------------------------------------
        if scope.get("method") == "OPTIONS":
            resp = JSONResponse(
                {},
                status_code=200,
                headers={**self._CORS, "Access-Control-Max-Age": "86400"},
            )
            await resp(scope, receive, send)
            return

        # --- authenticate ---------------------------------------------------
        request = Request(scope)
        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            response = JSONResponse(
                {"detail": "Missing Bearer token"},
                status_code=401,
                headers=self._CORS,
            )
            await response(scope, receive, send)
            return

        api_key = auth_header[7:]
        if not verify_key(api_key):
            response = JSONResponse(
                {"detail": "Invalid or revoked MCP API key"},
                status_code=401,
                headers=self._CORS,
            )
            await response(scope, receive, send)
            return

        # --- delegate to transport ------------------------------------------
        if self._transport is None:
            response = JSONResponse(
                {"detail": "MCP endpoint not ready"},
                status_code=503,
                headers=self._CORS,
            )
            await response(scope, receive, send)
            return

        # Wrap send to inject CORS headers on all transport responses
        async def send_with_cors(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                # Add CORS headers if not already present
                cors_names = {
                    b"access-control-allow-origin",
                    b"access-control-allow-methods",
                    b"access-control-allow-headers",
                }
                existing_cors = {name.lower() for name, _ in headers}
                if not existing_cors & cors_names:
                    for key, value in self._CORS.items():
                        headers.append((key.lower().encode(), value.encode()))
                message["headers"] = headers
            await send(message)

        await self._transport.handle_request(scope, receive, send_with_cors)


# Module-level singleton — mounted by ``news48.web.app``.
mcp_endpoint = MCPEndpoint()
