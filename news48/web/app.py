"""FastAPI web application with routes for the news48 web interface."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage MCP endpoint lifecycle."""
    await mcp_endpoint.startup()
    yield
    await mcp_endpoint.shutdown()


app = FastAPI(title="news48", lifespan=lifespan)
app.mount("/mcp", mcp_endpoint)


def _site_url(request: Request) -> str:
    return str(request.base_url).rstrip("/")


def _default_meta(request: Request) -> dict[str, object]:
    site_url = _site_url(request)
    canonical_url = build_canonical_url(site_url, str(request.url.path))
    seo = build_seo_meta(
        title="Live AI-Verified News and Fact-Checked Stories | news48",
        description=(
            "Browse live news from the last 48 hours with AI-rewritten "
            "summaries, source links, fact-check signals, and topic clusters."
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

# Templates with custom filters and caching disabled
templates = Jinja2Templates(directory=_web_dir / "templates")
templates.env.cache = None
templates.env.globals["app_version"] = __version__
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
    from news48.core.database.articles import (
        get_all_categories,
        get_articles_paginated,
        get_expiring_articles,
        get_topic_clusters,
        get_web_stats,
    )

    stats = get_web_stats(hours=48, parsed=True)
    stories, _ = get_articles_paginated(
        hours=48, limit=35, include_source=True, parsed=True
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
            name="Live AI-verified news in the last 48 hours",
            description=(
                "Fresh live news with AI-rewritten summaries, topic clusters, "
                "and source transparency."
            ),
            url=canonical_url,
            items=[
                {
                    "title": story.get("title"),
                    "canonical_url": build_canonical_url(
                        site_url, f"/article/{story['id']}"
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
            "seo": seo,
        },
    )


@app.get("/article/{article_id}")
async def article_detail(request: Request, article_id: int):
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
    article["canonical_url"] = build_canonical_url(site_url, f"/article/{article_id}")
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
                        site_url, f"/article/{item['id']}"
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


@app.get("/category/{category_slug}")
async def category_detail(request: Request, category_slug: str):
    """Category detail page showing all articles matching a category."""
    from news48.core.database.articles import (
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
    site_url = _site_url(request)
    canonical_url = build_canonical_url(site_url, f"/category/{category_slug}")
    category_title = (
        f"{category_name} News Today | Live Verified Stories " "in the Last 48 Hours"
    )
    category_description = (
        f"Explore the latest {category_name} news from the last 48 hours "
        "with rewritten coverage, source transparency, and fast access "
        "to related stories."
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
                        site_url, f"/article/{item['id']}"
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
        }
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
            site_url, f"/article/{article['id']}"
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
