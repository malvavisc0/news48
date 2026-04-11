"""Sitemap sub-app - generate sitemap.xml for search engines."""

import typer

from database import get_articles_paginated, init_database

from ._common import emit_error, require_db

sitemap_app = typer.Typer(help="Generate sitemap.xml for search engines.")


@sitemap_app.command(name="generate")
def generate_sitemap_cmd(
    output: str = typer.Option(
        "sitemap.xml", "--output", "-o", help="Output file path"
    ),
    site_url: str = typer.Option(..., "--site-url", help="Base URL of the website"),
) -> None:
    """Generate sitemap.xml for search engines."""
    db_path = require_db()
    init_database(db_path)

    try:
        from helpers.seo import generate_sitemap

        # Fetch all articles within 48h
        articles, total = get_articles_paginated(
            db_path,
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
