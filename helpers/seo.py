"""SEO and social sharing metadata helpers."""

import re
from datetime import datetime
from html import unescape
from xml.etree.ElementTree import Element, SubElement, tostring


def clean_text(value: str | None, limit: int | None = None) -> str:
    """Normalize whitespace and optionally trim text for metadata."""
    text = unescape(value or "")
    text = re.sub(r"\s+", " ", text).strip()
    if limit and len(text) > limit:
        trimmed = text[: limit - 1].rsplit(" ", 1)[0].strip()
        return f"{trimmed or text[: limit - 1].strip()}…"
    return text


def slug_to_name(slug: str) -> str:
    """Convert URL slug to readable title case text."""
    return clean_text(slug.replace("-", " ")).title()


def build_canonical_url(site_url: str, path: str) -> str:
    """Build an absolute canonical URL from a relative path."""
    base = site_url.rstrip("/")
    rel = path if path.startswith("/") else f"/{path}"
    return f"{base}{rel}"


def build_seo_meta(
    *,
    title: str,
    description: str,
    canonical_url: str,
    robots: str = (
        "index,follow,max-image-preview:large," "max-snippet:-1,max-video-preview:-1"
    ),
    og_type: str = "website",
    image_url: str | None = None,
) -> dict[str, object]:
    """Build normalized page-level SEO metadata."""
    clean_title = clean_text(title, 65)
    clean_description = clean_text(description, 160)
    og_tags: dict[str, str] = {
        "og:title": clean_title,
        "og:description": clean_description,
        "og:url": canonical_url,
        "og:type": og_type,
        "twitter:card": "summary_large_image" if image_url else "summary",
        "twitter:title": clean_title,
        "twitter:description": clean_description,
    }
    meta: dict[str, object] = {
        "title": clean_title,
        "description": clean_description,
        "canonical_url": canonical_url,
        "robots": robots,
        "og_tags": og_tags,
    }
    if image_url:
        og_tags["og:image"] = image_url
        og_tags["twitter:image"] = image_url
    return meta


def build_breadcrumb_schema(items: list[tuple[str, str]]) -> dict:
    """Build breadcrumb structured data."""
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": position,
                "name": name,
                "item": url,
            }
            for position, (name, url) in enumerate(items, start=1)
        ],
    }


def build_collection_schema(
    *,
    name: str,
    description: str,
    url: str,
    items: list[dict],
) -> dict:
    """Build collection page structured data."""
    return {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": clean_text(name, 110),
        "description": clean_text(description, 200),
        "url": url,
        "mainEntity": {
            "@type": "ItemList",
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": index,
                    "url": item.get("canonical_url") or item.get("url") or "",
                    "name": clean_text(item.get("title"), 110),
                }
                for index, item in enumerate(items, start=1)
                if item.get("title")
            ],
        },
    }


def build_website_schema(site_url: str) -> dict:
    """Build website structured data."""
    return {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": "news48",
        "url": site_url.rstrip("/"),
        "description": (
            "Live AI-verified news from the last 48 hours with "
            "source transparency, fact-check signals, and topic clusters."
        ),
        "publisher": {
            "@type": "Organization",
            "name": "news48",
            "url": site_url.rstrip("/"),
        },
    }


def generate_og_tags(article: dict, site_url: str) -> dict[str, str]:
    """Generate Open Graph meta tags for an article.

    Returns dict with keys:
    - og:title, og:description, og:image, og:url, og:type
    - twitter:card, twitter:title, twitter:description, twitter:image
    - article:published_time, article:author, article:section,
      article:tag
    """
    title = clean_text(article.get("title") or "Untitled", 110)
    summary = clean_text(article.get("summary") or article.get("content") or "", 200)
    image_url = article.get("image_url") or ""
    article_url = article.get("canonical_url") or article.get("url", "")
    author = article.get("author") or ""
    published_at = article.get("published_at") or ""
    categories = article.get("categories") or ""
    tags = article.get("tags") or ""

    # Build the article URL relative to site
    if article_url and not article_url.startswith("http"):
        article_url = f"{site_url.rstrip('/')}/article/{article['id']}"

    tags_dict: dict[str, str] = {
        "og:title": title,
        "og:description": summary,
        "og:url": article_url,
        "og:type": "article",
        "twitter:card": "summary_large_image",
        "twitter:title": title,
        "twitter:description": summary,
    }

    if image_url:
        tags_dict["og:image"] = image_url
        tags_dict["twitter:image"] = image_url

    if published_at:
        tags_dict["article:published_time"] = published_at

    if author:
        tags_dict["article:author"] = author

    if categories:
        # Use first category as section
        first_cat = categories.split(",")[0].strip()
        if first_cat:
            tags_dict["article:section"] = first_cat

    if tags:
        tags_dict["article:tag"] = tags

    return tags_dict


def generate_json_ld(article: dict, site_url: str) -> dict:
    """Generate JSON-LD structured data for Google News.

    Returns a NewsArticle schema dict:
    - @type: NewsArticle
    - headline, image, datePublished, dateModified
    - author, publisher, description, mainEntityOfPage
    """
    title = clean_text(article.get("title") or "Untitled", 110)
    summary = clean_text(article.get("summary") or article.get("content") or "", 300)
    image_url = article.get("image_url")
    author = article.get("author") or article.get("source_name")
    published_at = article.get("published_at")
    parsed_at = article.get("parsed_at")
    article_url = article.get("canonical_url") or article.get("url", "")
    categories = [
        clean_text(part)
        for part in str(article.get("categories") or "").split(",")
        if clean_text(part)
    ]
    keywords = [
        clean_text(part)
        for part in str(article.get("tags") or "").split(",")
        if clean_text(part)
    ]

    if article_url and not article_url.startswith("http"):
        article_url = f"{site_url.rstrip('/')}/article/{article['id']}"

    schema: dict = {
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "headline": title,
        "description": summary,
        "mainEntityOfPage": article_url,
        "isAccessibleForFree": True,
    }

    if image_url:
        schema["image"] = image_url

    if published_at:
        schema["datePublished"] = published_at

    if parsed_at:
        schema["dateModified"] = parsed_at

    if author:
        schema["author"] = {
            "@type": "Organization",
            "name": author,
        }

    if categories:
        schema["articleSection"] = categories[0]

    if keywords:
        schema["keywords"] = keywords

    schema["publisher"] = {
        "@type": "Organization",
        "name": "news48",
        "logo": {
            "@type": "ImageObject",
            "url": f"{site_url.rstrip('/')}/logo.png",
        },
    }

    return schema


def generate_sitemap(
    articles: list[dict],
    site_url: str,
    changefreq: str = "hourly",
    extra_urls: list[dict] | None = None,
) -> str:
    """Generate XML sitemap for search engines.

    Includes:
    - <url><loc> for each article
    - <lastmod> from published_at
    - <changefreq> hourly (news changes frequently)
    - <priority> 0.8 for articles, 1.0 for breaking/featured
    """
    urlset = Element("urlset")
    urlset.set("xmlns", "http://www.sitemaps.org/schemas/sitemap/0.9")

    base = site_url.rstrip("/")

    all_urls = list(extra_urls or []) + list(articles)

    for article in all_urls:
        url_elem = SubElement(urlset, "url")

        loc = SubElement(url_elem, "loc")
        article_url = article.get("canonical_url") or article.get("url", "")
        if article_url and article_url.startswith("http"):
            loc.text = article_url
        else:
            if article.get("id") is not None:
                loc.text = f"{base}/article/{article['id']}"
            else:
                loc.text = f"{base}/"

        # lastmod
        published = article.get("published_at")
        if published:
            lastmod = SubElement(url_elem, "lastmod")
            # Normalize to YYYY-MM-DD format
            try:
                dt = datetime.fromisoformat(published)
                lastmod.text = dt.strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                lastmod.text = str(published)[:10]

        # changefreq
        freq = SubElement(url_elem, "changefreq")
        freq.text = changefreq

        # priority
        priority = SubElement(url_elem, "priority")
        if article.get("priority"):
            priority.text = str(article["priority"])
        elif article.get("is_breaking") or article.get("is_featured"):
            priority.text = "1.0"
        else:
            priority.text = "0.8"

    xml_bytes = tostring(urlset, encoding="unicode", xml_declaration=True)
    return xml_bytes
