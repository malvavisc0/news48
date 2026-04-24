"""Sitemap sub-app - generate sitemap.xml for search engines."""

import typer

from news48.core.database import get_articles_paginated

from ._common import emit_error, require_db

sitemap_app = typer.Typer(help="Generate sitemap.xml for search engines.")


@sitemap_app.command(name="generate")
def generate_sitemap_cmd(
    output: str = typer.Option(
        "sitemap.xml", "--output", "-o", help="Output file path"
    ),
    site_url: str = typer.Option(
        ...,
        "--site-url",
        help="Base URL of the website (e.g. https://example.com)",
    ),
) -> None:
    """Generate sitemap.xml for search engines.

    Articles within the last 48 hours are included. The sitemap
    follows the XML Sitemaps protocol (sitemaps.org).

    Example:
        news48 sitemap generate --site-url https://news.example.com
    """
    require_db()

    try:
        from news48.core.helpers.seo import generate_sitemap

        # Fetch all articles within 48h
        articles, total = get_articles_paginated(
            limit=1000,
            hours=48,
            include_source=True,
        )

        xml = generate_sitemap(articles, site_url)

        with open(output, "w", encoding="utf-8") as f:
            f.write(xml)

        print(f"Generated {output} with {total} articles")
    except Exception as e:
        emit_error(str(e))
