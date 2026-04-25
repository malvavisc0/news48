"""Local MCP server exposing news48 operations as tools.

This server runs via stdio transport and is intended for use with
AI assistants like Claude Desktop, Cursor, etc.

All tool definitions and execution logic are in news48.mcp.tools,
shared with the remote HTTP endpoint.
"""

import logging

from mcp import types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from news48.mcp.tools import TOOLS, execute_tool

logger = logging.getLogger(__name__)

app = Server("news48")


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    """Return the list of available tools."""
    return TOOLS


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """Handle tool calls by delegating to the shared execution layer."""
    return await execute_tool(name, arguments, parsed_only=False)


async def main():
    """Run the MCP server via stdio transport."""
    async with stdio_server() as streams:
        await app.run(streams[0], streams[1], app.create_initialization_options())
