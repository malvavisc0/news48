"""FastAPI web application with routes for the news48 web interface."""

import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from news48 import __version__
from news48.core.database import collect_stats
from news48.core.helpers.seo import (
    build_canonical_url,
    build_seo_meta,
    generate_sitemap,
)
from news48.web.mcp.auth import verify_key
from news48.web.mcp.endpoint import mcp_endpoint

from .. import helpers as filters
from ._middleware import RateLimitMiddleware, SecurityHeadersMiddleware
from ._routes import (
    all_stories,
    article_detail,
    category_detail,
    cluster_detail,
    homepage,
    monitor,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage MCP endpoint lifecycle."""
    await mcp_endpoint.startup()
    yield
    await mcp_endpoint.shutdown()


app = FastAPI(title="news48", lifespan=lifespan, docs_url=None, redoc_url=None)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)

from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

app.add_middleware(
    CORSMiddleware,
    allow_origins=[],
    allow_methods=["GET"],
    allow_headers=[],
)

app.mount("/mcp", mcp_endpoint)

# Static files
_web_dir = Path(__file__).parent.parent
app.mount(
    "/static",
    StaticFiles(directory=_web_dir / "static"),
    name="static",
)

# Templates with custom filters.
templates = Jinja2Templates(directory=_web_dir / "templates")
if os.getenv("WEB_RELOAD", "0") == "1":
    templates.env.cache = None
templates.env.globals["app_version"] = __version__
templates.env.filters["relative_time"] = filters.format_relative_time
templates.env.filters["hours_remaining"] = filters.hours_remaining
templates.env.filters["freshness_class"] = filters.freshness_class
templates.env.filters["cluster_bar"] = filters.cluster_bar
templates.env.filters["word_count"] = filters.word_count
templates.env.filters["read_time"] = filters.read_time
templates.env.filters["parse_categories"] = filters.parse_categories
templates.env.filters["parse_tags"] = filters.parse_tags
templates.env.filters["format_category_name"] = filters.format_category_name


def _site_url(request: Request) -> str:
    return str(request.base_url).rstrip("/")


# ---------------------------------------------------------------------------
# Content routes (delegate to _routes handlers)
# ---------------------------------------------------------------------------


@app.get("/")
async def homepage_route(
    request: Request,
    sentiment: str | None = Query(None, pattern="^(positive|negative|neutral)$"),
):
    return await homepage(request, templates, filters, sentiment)


@app.get("/article/{article_id}/{slug}")
async def article_detail_route(request: Request, article_id: int, slug: str):
    return await article_detail(request, templates, article_id, slug)


@app.get("/cluster/{cluster_slug}")
async def cluster_detail_route(request: Request, cluster_slug: str):
    return await cluster_detail(request, templates, cluster_slug)


@app.get("/all")
async def all_stories_route(
    request: Request,
    sentiment: str | None = Query(None, pattern="^(positive|negative|neutral)$"),
):
    return await all_stories(request, templates, sentiment)


@app.get("/category/{category_slug}")
async def category_detail_route(
    request: Request,
    category_slug: str,
    sentiment: str | None = Query(None, pattern="^(positive|negative|neutral)$"),
):
    return await category_detail(request, templates, filters, category_slug, sentiment)


@app.get("/monitor")
async def monitor_route(request: Request):
    return await monitor(request, templates)


@app.get("/api/stats")
async def stats_api(request: Request, stale_days: int = Query(7, ge=1, le=30)):
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")

    api_key = auth_header[7:]
    if not verify_key(api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")

    return JSONResponse(collect_stats(stale_days))


# ---------------------------------------------------------------------------
# SEO / utility routes
# ---------------------------------------------------------------------------


@app.get("/robots.txt", response_class=PlainTextResponse)
async def robots(request: Request):
    site_url = _site_url(request)
    return "User-agent: *\n" "Allow: /\n" f"Sitemap: {site_url}/sitemap.xml\n"


@app.get("/sitemap.xml", response_class=PlainTextResponse)
async def sitemap(request: Request):
    from news48.core.database.articles import (
        get_all_categories,
        get_articles_paginated,
        get_topic_clusters,
    )

    site_url = _site_url(request)
    articles, _ = get_articles_paginated(
        hours=48, limit=250, include_source=True, parsed=True
    )
    categories = get_all_categories(hours=48, parsed=True)
    clusters = get_topic_clusters(hours=48, parsed=True)

    extra_urls = [
        {
            "canonical_url": build_canonical_url(site_url, "/"),
            "priority": "1.0",
            "changefreq": "hourly",
        },
        {
            "canonical_url": build_canonical_url(site_url, "/all"),
            "priority": "0.9",
            "changefreq": "hourly",
        },
    ]
    extra_urls.extend(
        {
            "canonical_url": build_canonical_url(
                site_url, f"/category/{category['slug']}"
            ),
            "priority": "0.9",
            "changefreq": "hourly",
        }
        for category in categories
    )
    extra_urls.extend(
        {
            "canonical_url": build_canonical_url(
                site_url, f"/cluster/{cluster['slug']}"
            ),
            "priority": "0.8",
            "changefreq": "hourly",
        }
        for cluster in clusters
    )

    for article in articles:
        article["canonical_url"] = build_canonical_url(
            site_url,
            "/article/{}/{}".format(article["id"], article.get("slug") or ""),
        )

    return generate_sitemap(articles, site_url, extra_urls=extra_urls)


@app.get("/llms.txt", response_class=PlainTextResponse)
async def llms_txt():
    llms_path = Path(__file__).parent.parent / "llms.txt"
    return llms_path.read_text(encoding="utf-8")


def _load_assessment() -> dict | None:
    """Load the latest autonomous operation score assessment."""
    assessment_path = (
        Path(__file__).parent.parent.parent.parent
        / ".scoring"
        / "latest-assessment.json"
    )
    try:
        return json.loads(assessment_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


@app.get("/docs")
async def docs_page(request: Request):
    mcp_domain = os.getenv("MCP_DOMAIN", "news48.io")
    seo = build_seo_meta(
        title="How news48 Works — Architecture & MCP Setup | news48",
        description=(
            "Learn how news48 ingests, verifies, and publishes autonomous "
            "news. MCP integration guide for Claude, Cursor, and other "
            "AI assistants."
        ),
        canonical_url=build_canonical_url(_site_url(request), "/docs"),
    )
    assessment = _load_assessment()
    return templates.TemplateResponse(
        request=request,
        name="docs.html",
        context={
            "seo": seo,
            "mcp_domain": mcp_domain,
            "assessment": assessment,
        },
    )


@app.get("/health")
async def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
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
    return templates.TemplateResponse(
        request=request,
        name="error.html",
        context={
            "title": "Server Error",
            "message": "Something went wrong. Please try again later.",
        },
        status_code=500,
    )
