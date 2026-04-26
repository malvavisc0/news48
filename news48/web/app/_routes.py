"""Content-heavy page routes.

Homepage, article, cluster, all stories, category, and monitor views.
"""

from fastapi import HTTPException, Request
from fastapi.templating import Jinja2Templates

from news48.core.database import collect_stats
from news48.core.helpers.seo import (
    build_breadcrumb_schema,
    build_canonical_url,
    build_collection_schema,
    build_seo_meta,
    build_website_schema,
    generate_json_ld,
    generate_og_tags,
)


def _site_url(request: Request) -> str:
    return str(request.base_url).rstrip("/")


def _default_meta(request: Request, templates: Jinja2Templates) -> dict[str, object]:
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


async def monitor(request: Request, templates: Jinja2Templates):
    """Internal monitor dashboard page with server-rendered stats."""
    site_url = _site_url(request)
    seo = build_seo_meta(
        title="news48 Monitor | Internal Dashboard",
        description=(
            "Operational dashboard for system health, pipeline throughput, "
            "feed coverage, and retention status."
        ),
        canonical_url=build_canonical_url(site_url, "/monitor"),
        robots="noindex,nofollow",
    )
    stats = collect_stats()
    return templates.TemplateResponse(
        request=request,
        name="monitor.html",
        context={
            "seo": seo,
            "stats": stats,
            "monitor_api_auth_hint": "Bearer token required for live refresh",
        },
    )


async def homepage(
    request: Request,
    templates: Jinja2Templates,
    filters,
    sentiment: str | None = None,
):
    """Homepage with curated stories, clusters, and expiring items."""
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

    max_cluster_count = max((c["article_count"] for c in clusters), default=10)
    site_url = _site_url(request)
    seo = _default_meta(request, templates)
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


async def article_detail(
    request: Request, templates: Jinja2Templates, article_id: int, slug: str
):
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


async def cluster_detail(
    request: Request, templates: Jinja2Templates, cluster_slug: str
):
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


async def all_stories(
    request: Request, templates: Jinja2Templates, sentiment: str | None = None
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


async def category_detail(
    request: Request,
    templates: Jinja2Templates,
    filters,
    category_slug: str,
    sentiment: str | None = None,
):
    """Category detail page showing all articles matching a category."""
    from news48.core.database.articles import (
        get_all_categories,
        get_articles_by_category,
        get_web_stats,
    )

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
