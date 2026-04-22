"""FastAPI web application with routes for the news48 web interface."""

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import web.helpers as filters

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
templates.env.filters["format_category_name"] = filters.format_category_name


@app.get("/")
async def homepage(request: Request):
    """Homepage with live stories, stats, clusters, expiring articles."""
    from database.articles import (
        get_all_categories,
        get_articles_paginated,
        get_expiring_articles,
        get_topic_clusters,
        get_web_stats,
    )

    stats = get_web_stats(hours=48, parsed=True)
    stories, _ = get_articles_paginated(
        hours=48, limit=20, include_source=True, parsed=True
    )
    clusters = get_topic_clusters(hours=48, parsed=True)
    expiring = get_expiring_articles(within_hours=6, parsed=True)
    categories = get_all_categories(hours=48, parsed=True)

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
            "categories": categories,
            "active_category": None,
        },
    )


@app.get("/article/{article_id}")
async def article_detail(request: Request, article_id: int):
    """Article detail page with fact-check claims and related stories."""
    from database.articles import (
        get_all_categories,
        get_article_detail,
        get_related_articles,
        increment_view_count,
    )
    from database.claims import get_claims_for_article
    from helpers.seo import generate_json_ld, generate_og_tags

    article = get_article_detail(article_id, parsed=True)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    claims = get_claims_for_article(article_id)
    related = get_related_articles(article_id, limit=3, parsed=True)
    categories = get_all_categories(hours=48, parsed=True)

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
        increment_view_count(article_id)
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
            "categories": categories,
            "active_category": None,
        },
    )


@app.get("/cluster/{cluster_slug}")
async def cluster_detail(request: Request, cluster_slug: str):
    """Cluster detail page showing all articles matching a tag."""
    from database.articles import get_all_categories, get_articles_by_tag

    articles, total = get_articles_by_tag(cluster_slug, hours=48, limit=50, parsed=True)
    if not articles:
        raise HTTPException(status_code=404, detail="Cluster not found")

    categories = get_all_categories(hours=48, parsed=True)

    return templates.TemplateResponse(
        request=request,
        name="cluster.html",
        context={
            "cluster_name": cluster_slug,
            "articles": articles,
            "total": total,
            "categories": categories,
            "active_category": None,
        },
    )


@app.get("/category/{category_slug}")
async def category_detail(request: Request, category_slug: str):
    """Category detail page showing all articles matching a category."""
    from database.articles import (
        get_all_categories,
        get_articles_by_category,
        get_web_stats,
    )

    articles, total = get_articles_by_category(
        category_slug, hours=48, limit=None, parsed=True
    )
    if not articles:
        raise HTTPException(status_code=404, detail="Category not found")

    categories = get_all_categories(hours=48, parsed=True)
    stats = get_web_stats(hours=48, parsed=True)

    # Look up display name from categories list
    cat_match = next((c for c in categories if c["slug"] == category_slug), None)
    raw_name = cat_match["name"] if cat_match else category_slug.replace("-", " ")
    category_name = filters.format_category_name(raw_name)

    return templates.TemplateResponse(
        request=request,
        name="category.html",
        context={
            "category_name": category_name,
            "category_slug": category_slug,
            "articles": articles,
            "total": total,
            "categories": categories,
            "active_category": category_slug,
            "stats": stats,
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
