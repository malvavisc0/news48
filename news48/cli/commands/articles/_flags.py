"""Article flag CLI commands: feature, breaking."""

import typer

from news48.core.database import (
    get_article_by_id,
    get_article_by_url,
    set_article_breaking,
    set_article_featured,
)

from .._common import emit_error, emit_json, require_db
from . import articles_app


@articles_app.command(name="feature")
def feature_article(
    identifier: str = typer.Argument(..., help="Article ID or URL"),
    remove: bool = typer.Option(False, "--remove", help="Remove featured status"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Mark an article as featured."""
    require_db()

    article = None
    try:
        article_id = int(identifier)
        article = get_article_by_id(article_id)
    except ValueError:
        article = get_article_by_url(identifier)

    if not article:
        emit_error(f"Article not found: {identifier}", as_json=output_json)

    featured = not remove
    set_article_featured(article["id"], featured=featured)

    data = {
        "id": article["id"],
        "url": article["url"],
        "title": article["title"],
        "is_featured": featured,
    }

    if output_json:
        emit_json(data)
    else:
        action = "Featured" if featured else "Unfeatured"
        print(f"{action} article: {article['title'] or 'Untitled'}")


@articles_app.command(name="breaking")
def breaking_article(
    identifier: str = typer.Argument(..., help="Article ID or URL"),
    remove: bool = typer.Option(False, "--remove", help="Remove breaking status"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Mark an article as breaking news."""
    require_db()

    article = None
    try:
        article_id = int(identifier)
        article = get_article_by_id(article_id)
    except ValueError:
        article = get_article_by_url(identifier)

    if not article:
        emit_error(f"Article not found: {identifier}", as_json=output_json)

    breaking = not remove
    set_article_breaking(article["id"], breaking=breaking)

    data = {
        "id": article["id"],
        "url": article["url"],
        "title": article["title"],
        "is_breaking": breaking,
    }

    if output_json:
        emit_json(data)
    else:
        action = "Marked breaking" if breaking else "Unmarked breaking"
        print(f"{action}: {article['title'] or 'Untitled'}")
