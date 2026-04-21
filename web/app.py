"""FastAPI web application with routes for the news48 web interface."""

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import web.helpers as filters
from config import Database

app = FastAPI(title="news48")

# Static files
_web_dir = Path(__file__).parent
app.mount(
    "/static",
    StaticFiles(directory=_web_dir / "static"),
    name="static",
)

# Templates with custom filters and caching disabled
templates = Jinja2Templates(directory=_web_dir / "templates")
templates.env.cache = None
templates.env.filters["relative_time"] = filters.format_relative_time
templates.env.filters["hours_remaining"] = filters.hours_remaining
templates.env.filters["freshness_class"] = filters.freshness_class
templates.env.filters["freshness_bar"] = filters.freshness_bar
templates.env.filters["cluster_bar"] = filters.cluster_bar
templates.env.filters["word_count"] = filters.word_count
templates.env.filters["read_time"] = filters.read_time
templates.env.filters["parse_categories"] = filters.parse_categories
templates.env.filters["parse_tags"] = filters.parse_tags

DB_PATH = Database.path


@app.get("/")
async def homepage(request: Request):
    """Homepage with live stories, stats, clusters, expiring articles."""
    from database.articles import (
        get_articles_paginated,
        get_expiring_articles,
        get_topic_clusters,
        get_web_stats,
    )

    stats = get_web_stats(DB_PATH, hours=48, parsed=True)
    stories, _ = get_articles_paginated(
        DB_PATH, hours=48, limit=20, include_source=True, parsed=True
    )
    clusters = get_topic_clusters(DB_PATH, hours=48, parsed=True)
    expiring = get_expiring_articles(DB_PATH, within_hours=6, parsed=True)

    # Compute max cluster count for proportional bar rendering
    max_cluster_count = max((c["article_count"] for c in clusters), default=10)

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "stats": stats,
            "stories": stories,
            "clusters": clusters,
            "expiring": expiring,
            "max_cluster_count": max_cluster_count,
        },
    )


@app.get("/article/{article_id}")
async def article_detail(request: Request, article_id: int):
    """Article detail page with fact-check claims and related stories."""
    from database.articles import (
        get_article_detail,
        get_related_articles,
        increment_view_count,
    )
    from database.claims import get_claims_for_article
    from helpers.seo import generate_json_ld, generate_og_tags

    article = get_article_detail(DB_PATH, article_id, parsed=True)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    claims = get_claims_for_article(DB_PATH, article_id)
    related = get_related_articles(DB_PATH, article_id, limit=3, parsed=True)

    # Compute claims summary from claims list
    claims_summary = {
        "verified": 0,
        "disputed": 0,
        "mixed": 0,
        "unverifiable": 0,
        "total": len(claims),
    }
    for claim in claims:
        verdict = claim.get("verdict", "unverifiable")
        if verdict in claims_summary:
            claims_summary[verdict] += 1

    # SEO metadata from existing helpers
    site_url = str(request.base_url).rstrip("/")
    og_tags = generate_og_tags(article, site_url)
    json_ld = generate_json_ld(article, site_url)

    # Increment view count - no rate limiting for v1
    try:
        increment_view_count(DB_PATH, article_id)
    except Exception:
        pass  # Non-critical; don't fail the request

    return templates.TemplateResponse(
        request=request,
        name="article.html",
        context={
            "article": article,
            "claims": claims,
            "claims_summary": claims_summary,
            "related": related,
            "og_tags": og_tags,
            "json_ld": json_ld,
        },
    )


@app.get("/cluster/{cluster_slug}")
async def cluster_detail(request: Request, cluster_slug: str):
    """Cluster detail page showing all articles matching a tag."""
    from database.articles import get_articles_by_tag

    articles, total = get_articles_by_tag(
        DB_PATH, cluster_slug, hours=48, limit=50, parsed=True
    )
    if not articles:
        raise HTTPException(status_code=404, detail="Cluster not found")

    return templates.TemplateResponse(
        request=request,
        name="cluster.html",
        context={
            "cluster_name": cluster_slug,
            "articles": articles,
            "total": total,
        },
    )


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}


# Custom exception handlers
@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    """Render custom 404 page."""
    return templates.TemplateResponse(
        request=request,
        name="error.html",
        context={
            "title": "Not Found",
            "message": "The article you are looking for does not exist "
            "or has expired.",
        },
        status_code=404,
    )


@app.exception_handler(500)
async def server_error_handler(request: Request, exc):
    """Render custom 500 page."""
    return templates.TemplateResponse(
        request=request,
        name="error.html",
        context={
            "title": "Server Error",
            "message": "Something went wrong. Please try again later.",
        },
        status_code=500,
    )
