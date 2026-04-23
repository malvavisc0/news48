"""News feed fetcher and article parser CLI.

This module provides a Typer-based CLI with commands:

- fetch: Fetch and parse RSS/Atom feeds from URLs stored in the database
  using feedparser.
- parse: Parse unparsed articles from the database and extract structured
  information using an LLM-based news parser agent.
- seed: Seed the database with feed URLs from a file.
- download: Download HTML content for articles.
- stats: Show system statistics.
- feeds: Manage feeds in the database (list, add, delete, info).
- articles: Manage articles in the database (list, info).
"""

import typer

from news48.cli.commands import (
    agents_app,
    articles_app,
    cleanup_app,
    download,
    feeds_app,
    fetch,
    fetches_app,
    lessons_app,
    logs_app,
    parse,
    plans_app,
    search_app,
    seed,
    sitemap_app,
    stats,
)
from news48.cli.commands.fact_check import fact_check

app = typer.Typer()
app.command()(fetch)
app.command()(parse)
app.command()(seed)
app.command()(download)
app.command(name="fact-check")(fact_check)
app.command()(stats)
app.add_typer(feeds_app, name="feeds")
app.add_typer(fetches_app, name="fetches")
app.add_typer(articles_app, name="articles")
app.add_typer(cleanup_app, name="cleanup")
app.add_typer(agents_app, name="agents")
app.add_typer(lessons_app, name="lessons")
app.add_typer(logs_app, name="logs")
app.add_typer(plans_app, name="plans")
app.add_typer(search_app, name="search")
app.add_typer(sitemap_app, name="sitemap")

# MCP subcommand group
mcp_app = typer.Typer()


@mcp_app.command("serve")
def mcp_serve():
    """Start the local MCP server (stdio transport)."""
    import asyncio

    from news48.mcp.server import main as mcp_main

    asyncio.run(mcp_main())


@mcp_app.command("create-key")
def mcp_create_key(
    label: str = typer.Option(None, help="Human-readable label for this key"),
):
    """Generate a new MCP API key and store it in Redis."""
    from news48.web.mcp.auth import create_key

    key = create_key(label=label)
    typer.echo(f"Created MCP API key: {key}")
    typer.echo("Store this key securely — it cannot be retrieved later.")


@mcp_app.command("revoke-key")
def mcp_revoke_key(
    api_key: str = typer.Argument(..., help="The full API key to revoke"),
):
    """Revoke an existing MCP API key."""
    from news48.web.mcp.auth import revoke_key

    if revoke_key(api_key):
        typer.echo("Key revoked successfully.")
    else:
        typer.echo("Key not found.")


@mcp_app.command("list-keys")
def mcp_list_keys():
    """List all active MCP API keys."""
    from rich.console import Console
    from rich.table import Table

    from news48.web.mcp.auth import list_keys

    keys = list_keys()
    if not keys:
        typer.echo(
            "No MCP API keys found. " "Create one with: news48 mcp create-key"
        )
        return
    table = Table(title="MCP API Keys")
    table.add_column("Key", style="cyan")
    table.add_column("Label", style="green")
    table.add_column("Created", style="dim")
    for k in keys:
        table.add_row(
            k["key"],
            k.get("label", "—"),
            k.get("created_at", "—"),
        )
    Console().print(table)


app.add_typer(mcp_app, name="mcp")


@app.command()
def serve(
    host: str | None = None,
    port: int | None = None,
):
    """Start the web server."""
    import uvicorn

    from news48.core.config import Web
    from news48.web.app import app as web_app

    uvicorn.run(
        web_app,
        host=host or Web.host,
        port=port or Web.get_port(),
    )


def main():
    app()


if __name__ == "__main__":
    main()
