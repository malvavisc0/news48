"""Search sub-app - full-text search across articles."""

import typer

from news48.core.database import search_articles

from ._common import emit_error, emit_json, require_db

search_app = typer.Typer(help="Full-text search across articles.")


@search_app.command(name="articles")
def search_articles_cmd(
    query: str = typer.Argument(..., help="Search query"),
    hours: int = typer.Option(48, "--hours", help="Time window in hours"),
    sentiment: str = typer.Option(
        None,
        "--sentiment",
        help="Filter by sentiment (positive, negative, neutral)",
    ),
    category: str = typer.Option(None, "--category", help="Filter by category"),
    limit: int = typer.Option(20, "--limit", "-l"),
    offset: int = typer.Option(0, "--offset", "-o"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Search articles using full-text search.

    Examples:
        news48 search articles "climate change"
        news48 search articles "election" --sentiment negative --limit 5
    """
    require_db()

    try:
        articles, total = search_articles(
            query=query,
            hours=hours,
            sentiment=sentiment,
            category=category,
            limit=limit,
            offset=offset,
        )
    except Exception as e:
        emit_error(str(e), as_json=output_json)

    article_list = []
    for a in articles:
        article_list.append(
            {
                "id": a["id"],
                "title": a["title"],
                "url": a["url"],
                "summary": a.get("summary"),
                "source_name": a.get("source_name"),
                "published_at": a.get("published_at"),
                "rank": a.get("rank"),
            }
        )

    data = {
        "query": query,
        "total": total,
        "limit": limit,
        "offset": offset,
        "articles": article_list,
    }

    if output_json:
        emit_json(data)
    else:
        print(f"Search: '{query}' — {len(article_list)} of {total}")
        for a in article_list:
            title = a["title"] or "Untitled"
            source = a.get("source_name") or "Unknown"
            print(f"  [{source}] {title}")
            print(f"    {a['url']}")
