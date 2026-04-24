"""FastAPI web application with routes for the news48 web interface."""

import time
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware

from news48 import __version__
from news48.core.helpers.seo import (
    build_breadcrumb_schema,
    build_canonical_url,
    build_collection_schema,
    build_seo_meta,
    build_website_schema,
    generate_json_ld,
    generate_og_tags,
    generate_sitemap,
)
from news48.web.mcp.endpoint import mcp_endpoint

from . import helpers as filters


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add standard security headers to all responses."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=()"
        )
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory rate limiter keyed by client IP.

    Limits:
    - General endpoints: 120 requests per minute
    - Search endpoint: 20 requests per minute

    Includes periodic sweep to remove stale IP entries and prevent
    unbounded memory growth under high-cardinality traffic.
    """

    _GENERAL_LIMIT = 120
    _SEARCH_LIMIT = 20
    _WINDOW = 60.0  # seconds
    _SWEEP_INTERVAL = 300.0  # full sweep every 5 minutes

    def __init__(self, app):
        super().__init__(app)
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._last_sweep: float = time.time()

    def _get_client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _cleanup(self, ip: str, now: float) -> None:
        cutoff = now - self._WINDOW
        self._requests[ip] = [t for t in self._requests[ip] if t > cutoff]

    def _maybe_sweep(self, now: float) -> None:
        """Remove empty IP entries to prevent unbounded dict growth."""
        if now - self._last_sweep < self._SWEEP_INTERVAL:
            return
        self._last_sweep = now
        empty_ips = [ip for ip, ts in self._requests.items() if not ts]
        for ip in empty_ips:
            del self._requests[ip]

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for static files and health check
        path = request.url.path
        if path.startswith("/static") or path == "/health":
            return await call_next(request)

        ip = self._get_client_ip(request)
        now = time.time()
        self._cleanup(ip, now)
        self._maybe_sweep(now)

        # Determine limit based on path
        if path.startswith("/search"):
            limit = self._SEARCH_LIMIT
        else:
            limit = self._GENERAL_LIMIT

        if len(self._requests[ip]) >= limit:
            return JSONResponse(
                {"detail": "Rate limit exceeded. Try again later."},
                status_code=429,
            )

        self._requests[ip].append(now)
        return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage MCP endpoint lifecycle."""
    await mcp_endpoint.startup()
    yield
    await mcp_endpoint.shutdown()


app = FastAPI(title="news48", lifespan=lifespan)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)

# CORS: restrictive by default. Only the MCP endpoint needs
# cross-origin access; web routes are server-rendered.
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

app.add_middleware(
    CORSMiddleware,
    allow_origins=[],  # No cross-origin for web routes
    allow_methods=["GET"],
    allow_headers=[],
)

app.mount("/mcp", mcp_endpoint)


def _site_url(request: Request) -> str:
    return str(request.base_url).rstrip("/")


def _default_meta(request: Request) -> dict[str, object]:
    site_url = _site_url(request)
    canonical_url = build_canonical_url(site_url, str(request.url.path))
    seo = build_seo_meta(
        title="AI-Verified News and Fact-Checked Stories | news48",
        description=(
            "Live news from the last 48 hours — clear summaries, "
            "automated fact-checks, and real-time topic discovery."
        ),
        canonical_url=canonical_url,
    )
    seo["json_ld"] = [build_website_schema(site_url)]
    return seo


def _seo_str(seo: dict[str, object], key: str) -> str:
    """Read a string value from the SEO metadata dict."""
    value = seo.get(key, "")
    return value if isinstance(value, str) else ""


# Static files
_web_dir = Path(__file__).parent
app.mount(
    "/static",
    StaticFiles(directory=_web_dir / "static"),
    name="static",
)

# Templates with custom filters.
# Caching is disabled only when WEB_RELOAD=1 (development mode).
import os  # noqa: E402

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


@app.get("/")
async def homepage(
    request: Request,
    sentiment: str | None = Query(None, pattern="^(positive|negative|neutral)$"),
):
    """Homepage with curated top-10 stories, stats, clusters, expiring articles."""
    from news48.core.database.articles import (
        get_all_categories,
        get_articles_paginated,
        get_expiring_articles,
        get_topic_clusters,
        get_web_stats,
    )

    stats = get_web_stats(hours=48, parsed=True)
    stories, _ = get_articles_paginated(
        hours=48,
        limit=10,
        include_source=True,
        parsed=True,
        sentiment=sentiment,
    )
    clusters = get_topic_clusters(hours=48, parsed=True)
    expiring = get_expiring_articles(within_hours=6, parsed=True)
    categories = get_all_categories(hours=48, parsed=True)

    # Compute max cluster count for proportional bar rendering
    max_cluster_count = max((c["article_count"] for c in clusters), default=10)
    site_url = _site_url(request)
    seo = _default_meta(request)
    canonical_url = _seo_str(seo, "canonical_url")
    seo["json_ld"] = [
        build_website_schema(site_url),
        build_collection_schema(
            name="AI-verified news in the last 48 hours",
            description=(
                "Fresh live news with AI-rewritten summaries, topic clusters, "
                "and source transparency."
            ),
            url=canonical_url,
            items=[
                {
                    "title": story.get("title"),
                    "canonical_url": build_canonical_url(
                        site_url,
                        "/article/{}/{}".format(story["id"], story.get("slug") or ""),
                    ),
                }
                for story in stories
            ],
        ),
    ]

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
            "active_sentiment": sentiment,
            "seo": seo,
        },
    )


@app.get("/article/{article_id}/{slug}")
async def article_detail(request: Request, article_id: int, slug: str):
    """Article detail page with fact-check claims and related stories."""
    from news48.core.database.articles import (
        get_all_categories,
        get_article_detail,
        get_related_articles,
        increment_view_count,
    )
    from news48.core.database.claims import get_claims_for_article

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

    site_url = _site_url(request)
    article["canonical_url"] = build_canonical_url(
        site_url,
        "/article/{}/{}".format(article_id, article.get("slug") or ""),
    )
    seo = build_seo_meta(
        title=f"{article['title']} | news48",
        description=(
            article.get("summary")
            or (
                "Read the rewritten article, review the original source, "
                "and see fact-check context on news48."
            )
        ),
        canonical_url=article["canonical_url"],
        og_type="article",
        image_url=article.get("image_url"),
    )
    seo["og_tags"] = generate_og_tags(article, site_url)
    seo["json_ld"] = [
        generate_json_ld(article, site_url),
        build_breadcrumb_schema(
            [
                ("Home", build_canonical_url(site_url, "/")),
                (article["title"], article["canonical_url"]),
            ]
        ),
    ]

    # Increment view count (non-critical; don't fail the request)
    try:
        increment_view_count(article_id)
    except Exception:
        pass

    return templates.TemplateResponse(
        request=request,
        name="article.html",
        context={
            "article": article,
            "claims": claims,
            "claims_summary": claims_summary,
            "related": related,
            "categories": categories,
            "active_category": None,
            "seo": seo,
        },
    )


@app.get("/cluster/{cluster_slug}")
async def cluster_detail(request: Request, cluster_slug: str):
    """Cluster detail page showing all articles matching a tag."""
    from news48.core.database.articles import get_all_categories, get_articles_by_tag

    articles, total = get_articles_by_tag(
        cluster_slug, hours=48, limit=None, parsed=True
    )
    if not articles:
        raise HTTPException(status_code=404, detail="Cluster not found")

    categories = get_all_categories(hours=48, parsed=True)
    site_url = _site_url(request)
    cluster_name = cluster_slug.replace("-", " ").title()
    canonical_url = build_canonical_url(site_url, f"/cluster/{cluster_slug}")
    cluster_description = (
        f"Track the latest coverage on {cluster_name} with grouped stories, "
        "rewritten summaries, and source links for quick comparison."
    )
    seo = build_seo_meta(
        title=f"{cluster_name} News and Related Coverage | news48",
        description=cluster_description,
        canonical_url=canonical_url,
    )
    seo["json_ld"] = [
        build_collection_schema(
            name=f"{cluster_name} news coverage",
            description=cluster_description,
            url=canonical_url,
            items=[
                {
                    "title": item.get("title"),
                    "canonical_url": build_canonical_url(
                        site_url,
                        "/article/{}/{}".format(item["id"], item.get("slug") or ""),
                    ),
                }
                for item in articles
            ],
        ),
        build_breadcrumb_schema(
            [
                ("Home", build_canonical_url(site_url, "/")),
                (cluster_name, canonical_url),
            ]
        ),
    ]

    return templates.TemplateResponse(
        request=request,
        name="cluster.html",
        context={
            "cluster_name": cluster_name,
            "articles": articles,
            "total": total,
            "categories": categories,
            "active_category": None,
            "seo": seo,
        },
    )


@app.get("/all")
async def all_stories(
    request: Request,
    sentiment: str | None = Query(None, pattern="^(positive|negative|neutral)$"),
):
    """All stories page — shows every parsed article with optional sentiment filter."""
    from news48.core.database.articles import (
        get_all_categories,
        get_articles_paginated,
        get_web_stats,
    )

    articles, total = get_articles_paginated(
        hours=48,
        limit=None,
        include_source=True,
        parsed=True,
        sentiment=sentiment,
    )
    categories = get_all_categories(hours=48, parsed=True)
    stats = get_web_stats(hours=48, parsed=True)

    site_url = _site_url(request)
    canonical_url = build_canonical_url(site_url, "/all")
    seo = build_seo_meta(
        title="All Stories — Live Verified News | news48",
        description=(
            "Every live news story from the last 48 hours — "
            "clear summaries, source transparency, and fact-check signals."
        ),
        canonical_url=canonical_url,
    )
    seo["json_ld"] = [
        build_collection_schema(
            name="All live news stories",
            description=(
                "All fresh live news with AI-rewritten summaries, "
                "topic clusters, and source transparency."
            ),
            url=canonical_url,
            items=[
                {
                    "title": item.get("title"),
                    "canonical_url": build_canonical_url(
                        site_url,
                        "/article/{}/{}".format(item["id"], item.get("slug") or ""),
                    ),
                }
                for item in articles
            ],
        ),
        build_breadcrumb_schema(
            [
                ("Home", build_canonical_url(site_url, "/")),
                ("All Stories", canonical_url),
            ]
        ),
    ]

    return templates.TemplateResponse(
        request=request,
        name="all.html",
        context={
            "articles": articles,
            "total": total,
            "categories": categories,
            "active_category": "all",
            "active_sentiment": sentiment,
            "stats": stats,
            "seo": seo,
        },
    )


@app.get("/category/{category_slug}")
async def category_detail(
    request: Request,
    category_slug: str,
    sentiment: str | None = Query(None, pattern="^(positive|negative|neutral)$"),
):
    """Category detail page showing all articles matching a category."""
    from news48.core.database.articles import (
        get_all_categories,
        get_articles_by_category,
        get_web_stats,
    )

    # First check the category exists (without sentiment filter)
    _, unfiltered_total = get_articles_by_category(
        category_slug, hours=48, limit=0, parsed=True, sentiment=None
    )
    if not unfiltered_total:
        raise HTTPException(status_code=404, detail="Category not found")

    articles, total = get_articles_by_category(
        category_slug, hours=48, limit=None, parsed=True, sentiment=sentiment
    )

    categories = get_all_categories(hours=48, parsed=True)
    stats = get_web_stats(hours=48, parsed=True)

    # Look up display name from categories list
    cat_match = next((c for c in categories if c["slug"] == category_slug), None)
    raw_name = cat_match["name"] if cat_match else category_slug.replace("-", " ")
    category_name = filters.format_category_name(raw_name)
    site_url = _site_url(request)
    canonical_url = build_canonical_url(site_url, f"/category/{category_slug}")
    category_title = (
        f"{category_name} News Today | Live Verified Stories " "in the Last 48 Hours"
    )
    category_description = (
        f"The latest {category_name} news from the last 48 hours — "
        "clear summaries, source transparency, and related stories."
    )
    seo = build_seo_meta(
        title=category_title,
        description=category_description,
        canonical_url=canonical_url,
    )
    seo["json_ld"] = [
        build_collection_schema(
            name=f"{category_name} news",
            description=category_description,
            url=canonical_url,
            items=[
                {
                    "title": item.get("title"),
                    "canonical_url": build_canonical_url(
                        site_url,
                        "/article/{}/{}".format(item["id"], item.get("slug") or ""),
                    ),
                }
                for item in articles
            ],
        ),
        build_breadcrumb_schema(
            [
                ("Home", build_canonical_url(site_url, "/")),
                (category_name, canonical_url),
            ]
        ),
    ]

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
            "active_sentiment": sentiment,
            "stats": stats,
            "seo": seo,
        },
    )


@app.get("/robots.txt", response_class=PlainTextResponse)
async def robots(request: Request):
    """Robots directives for crawlers."""
    site_url = _site_url(request)
    return "User-agent: *\n" "Allow: /\n" f"Sitemap: {site_url}/sitemap.xml\n"


@app.get("/sitemap.xml", response_class=PlainTextResponse)
async def sitemap(request: Request):
    """XML sitemap for key indexable pages."""
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
