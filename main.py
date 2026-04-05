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

from commands.agents import agents_app
from commands.articles import articles_app
from commands.cleanup import cleanup_app
from commands.download import download
from commands.feeds import feeds_app
from commands.fetch import fetch
from commands.fetches import fetches_app
from commands.parse import parse
from commands.search import search_app
from commands.seed import seed
from commands.sitemap import sitemap_app
from commands.stats import stats

app = typer.Typer()
app.command()(fetch)
app.command()(parse)
app.command()(seed)
app.command()(download)
app.command()(stats)
app.add_typer(feeds_app, name="feeds")
app.add_typer(fetches_app, name="fetches")
app.add_typer(articles_app, name="articles")
app.add_typer(cleanup_app, name="cleanup")
app.add_typer(agents_app, name="agents")
app.add_typer(search_app, name="search")
app.add_typer(sitemap_app, name="sitemap")


def main():
    app()


if __name__ == "__main__":
    main()
