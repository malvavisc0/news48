"""News feed fetcher and article parser CLI.

This module provides a Typer-based CLI with commands:

- fetch: Fetch and parse RSS/Atom feeds from URLs stored in the database
  using feedparser.
- parse: Parse unparsed articles from the database and extract structured
  information using an LLM-based news parser agent.
- seed: Seed the database with feed URLs from a file.
- runs: List recent fetch runs from the database.
- feeds: Manage feeds in the database (list, add, delete, info).
"""

import typer

from commands.download import download
from commands.feeds import feeds_app
from commands.fetch import fetch
from commands.parse import parse
from commands.seed import seed
from commands.stats import stats

app = typer.Typer()
app.command()(fetch)
app.command()(parse)
app.command()(seed)
app.command()(download)
app.command()(stats)
app.add_typer(feeds_app, name="feeds")


def main():
    app()


if __name__ == "__main__":
    main()
