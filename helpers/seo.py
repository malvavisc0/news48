"""SEO and social sharing metadata helpers."""

from datetime import datetime
from xml.etree.ElementTree import Element, SubElement, tostring


def generate_og_tags(article: dict, site_url: str) -> dict[str, str]:
    """Generate Open Graph meta tags for an article.

    Returns dict with keys:
    - og:title, og:description, og:image, og:url, og:type
    - twitter:card, twitter:title, twitter:description, twitter:image
    - article:published_time, article:author, article:section,
      article:tag
    """
    title = article.get("title") or "Untitled"
    summary = article.get("summary") or ""
    image_url = article.get("image_url") or ""
    article_url = article.get("url", "")
    author = article.get("author") or ""
    published_at = article.get("published_at") or ""
    categories = article.get("categories") or ""
    tags = article.get("tags") or ""

    # Build the article URL relative to site
    if article_url and not article_url.startswith("http"):
        article_url = f"{site_url.rstrip('/')}/article/{article['id']}"

    tags_dict: dict[str, str] = {
        "og:title": title,
        "og:description": summary[:200],
        "og:url": article_url,
        "og:type": "article",
        "twitter:card": "summary_large_image",
        "twitter:title": title,
        "twitter:description": summary[:200],
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
    title = article.get("title") or "Untitled"
    summary = article.get("summary") or ""
    image_url = article.get("image_url")
    author = article.get("author") or article.get("source_name")
    published_at = article.get("published_at")
    parsed_at = article.get("parsed_at")
    article_url = article.get("url", "")

    if article_url and not article_url.startswith("http"):
        article_url = f"{site_url.rstrip('/')}/article/{article['id']}"

    schema: dict = {
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "headline": title,
        "description": summary,
        "mainEntityOfPage": article_url,
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

    for article in articles:
        url_elem = SubElement(urlset, "url")

        loc = SubElement(url_elem, "loc")
        article_url = article.get("url", "")
        if article_url and article_url.startswith("http"):
            loc.text = article_url
        else:
            loc.text = f"{base}/article/{article['id']}"

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
        if article.get("is_breaking") or article.get("is_featured"):
            priority.text = "1.0"
        else:
            priority.text = "0.8"

    xml_bytes = tostring(urlset, encoding="unicode", xml_declaration=True)
    return xml_bytes
