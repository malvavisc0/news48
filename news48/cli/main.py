"""News48 — Autonomous news ingestion and verification pipeline.

This CLI is the primary interface for the news48 pipeline. The typical
workflow is:

  1. seed    — Load feed URLs into the database from a seed file
  2. fetch   — Pull RSS/Atom entries from those feeds
  3. download— Fetch full article HTML (with bypass for anti-bot walls)
  4. parse   — Extract structured data via an LLM parser agent
  5. fact-check — Verify claims against external evidence

Autonomous agents (sentinel, executor, parser, fact_checker) can run
these steps automatically via Dramatiq workers.

Run ``news48 <command> --help`` for details on any command.
"""

import typer

from news48.cli.commands import (
    agents_app,
    articles_app,
    briefing,
    cleanup_app,
    download,
    feeds_app,
    fetch,
    fetches_app,
    lessons_app,
    parse,
    plans_app,
    search_app,
    seed,
    stats,
)
from news48.cli.commands.fact_check import fact_check

app = typer.Typer(
    help=(
        "News48 — Autonomous news ingestion and verification pipeline.\n\n"
        "WORKFLOW:\n"
        "  1. news48 seed seed.txt     Load feed URLs\n"
        "  2. news48 fetch             Pull RSS/Atom entries\n"
        "  3. news48 download          Fetch full article content\n"
        "  4. news48 parse             Extract structured data via LLM\n"
        "  5. news48 fact-check        Verify claims against evidence\n\n"
        "Run 'news48 <command> --help' for details on any command.\n"
        "Most commands support '--json' for machine-readable output."
    ),
)
app.command()(fetch)
app.command()(parse)
app.command()(seed)
app.command()(download)
app.command(name="fact-check")(fact_check)
app.command()(stats)
app.command()(briefing)
app.add_typer(feeds_app, name="feeds")
app.add_typer(fetches_app, name="fetches")
app.add_typer(articles_app, name="articles")
app.add_typer(cleanup_app, name="cleanup")
app.add_typer(agents_app, name="agents")
app.add_typer(lessons_app, name="lessons")
app.add_typer(plans_app, name="plans")
app.add_typer(search_app, name="search")

# MCP subcommand group
mcp_app = typer.Typer(
    help="Manage the MCP (Model Context Protocol) server and API keys."
)


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
        typer.echo("No MCP API keys found. " "Create one with: news48 mcp create-key")
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


def main():
    app()


if __name__ == "__main__":
    main()
