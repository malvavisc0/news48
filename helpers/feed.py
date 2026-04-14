"""Feed fetching and date utilities."""

import asyncio
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, List

import dateparser
import feedparser

from database import (
    complete_fetch,
    create_fetch,
    fail_fetch,
    get_feed_by_url,
    insert_articles,
    update_feed_metadata,
)
from models import FeedEntry, FeedResult, FeedSummary


def _strip_html_tags(text: str | None) -> str | None:
    """Remove any HTML tags from text."""
    if not text:
        return text
    return re.sub(r"<[^>]+>", "", text).strip()


def is_article_from_last_48_hours(published_at: str | None) -> bool:
    """Check if an article was published within the last 48 hours.

    Args:
        published_at: The publication date string from the feed entry.
                    Can be in various formats (ISO 8601, RFC 2822, etc.)

    Returns:
        True if the article was published within the last 48 hours,
        False if the article is older or if published_at is None/empty.
    """
    if not published_at:
        return False

    try:
        # Parse the date string - feedparser returns dates in various formats
        # We try common formats used in RSS/Atom feeds
        article_date = _parse_feed_date(published_at)
        if article_date is None:
            return False

        # Get current date in UTC
        now = datetime.now(timezone.utc)

        # Calculate the difference
        age = now - article_date

        # Article must be published within the last 48 hours.
        # Explicitly exclude future-dated timestamps (clock skew / publisher
        # error) to avoid processing articles that aren't yet available.
        return timedelta(hours=0) <= age <= timedelta(hours=48)
    except Exception:
        # If we can't parse the date, skip the article
        return False


def _parse_feed_date(date_str: str) -> datetime | None:
    """Parse date string from RSS/Atom feed into datetime.

    Uses dateparser library for flexible date parsing.

    Args:
        date_str: The date string to parse.

    Returns:
        A datetime object with UTC timezone, or None if parsing fails.
    """
    dt = dateparser.parse(date_str)
    if dt is None:
        return None
    # Ensure timezone is set (dateparser may return naive datetime)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def normalize_published_date(date_str: str | None) -> str | None:
    """Parse various date formats and normalize to UTC ISO 8601.

    Wraps the existing _parse_feed_date() but returns ISO string.
    Uses dateparser (already a project dependency) with UTC timezone
    setting.

    Handles:
    - RFC 822 / RFC 3339
    - ISO 8601 with/without timezone
    - Relative dates
    - Various locale formats
    """
    if not date_str:
        return None
    dt = _parse_feed_date(date_str)
    return dt.isoformat() if dt else None


def load_urls(filepath: str) -> List[str]:
    """Load URLs from a file, one per line.

    Args:
        filepath: Path to the file containing URLs.

    Returns:
        A list of URLs, one per line, with whitespace stripped.
    """
    with open(filepath, encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


async def _fetch_with_semaphore(
    url: str,
    sem: asyncio.Semaphore,
) -> FeedResult:
    """Fetch a single feed under a semaphore."""
    async with sem:
        return await _fetch_feed(url)


async def get_fetch_summary(
    urls: List[str],
    delay: float,
    db_path: Path | None = None,
    on_feed_done: Callable[[FeedResult], None] | None = None,
) -> FeedSummary:
    """Fetch multiple feeds and return a summary of results.

    Args:
        urls: List of feed URLs to fetch.
        delay: Delay between requests in seconds
            (deprecated, kept for API compat).
        db_path: Optional path to SQLite database for tracking.
        on_feed_done: Optional callback invoked after each feed is
            fetched, receiving the FeedResult.

    Returns:
        A FeedSummary containing successful and failed feed results.
    """
    summary = FeedSummary()
    fetch_id = None

    if db_path:
        fetch_id = create_fetch(db_path)

    try:
        # Fetch all feeds concurrently with a semaphore limiting parallelism
        sem = asyncio.Semaphore(10)
        tasks = [_fetch_with_semaphore(url, sem) for url in urls]
        results = await asyncio.gather(*tasks)

        for result in results:
            summary.add_result(result)
            if on_feed_done:
                on_feed_done(result)

            if db_path and fetch_id and result.success:
                url = result.url
                feed = get_feed_by_url(db_path, url)
                if feed:
                    update_feed_metadata(
                        db_path,
                        feed["id"],
                        result.title or "Unknown",
                        favicon_url=extract_favicon(url),
                    )
                    # Filter: only articles from current month or later
                    articles = [
                        entry.model_dump()
                        for entry in result.entries
                        if is_article_from_last_48_hours(entry.published_at)
                    ]
                    # Each function manages its own connection
                    insert_articles(
                        db_path,
                        fetch_id,
                        feed["id"],
                        articles,
                        source_name=result.title,
                    )

        if db_path and fetch_id:
            complete_fetch(
                db_path,
                fetch_id,
                len(urls),
                sum(r.valid_articles_count for r in summary.successful),
            )
    except Exception:
        if db_path and fetch_id:
            fail_fetch(db_path, fetch_id)
        raise

    return summary


async def _fetch_feed(url: str) -> FeedResult:
    """Fetch and parse an RSS/Atom feed from a URL.

    Args:
        url: The URL of the feed to fetch.

    Returns:
        A FeedResult with the parsed feed data or error information.
    """
    try:
        loop = asyncio.get_running_loop()
        feed = await loop.run_in_executor(None, feedparser.parse, url)
        return _process_feed(feed, url)
    except Exception as e:
        return FeedResult(url=url, success=False, error=str(e))


def _process_feed(feed: feedparser.FeedParserDict, url: str) -> FeedResult:
    """Process a parsed feed and return a result.

    Args:
        feed: The parsed feed dictionary from feedparser.
        url: The original URL of the feed.

    Returns:
        A FeedResult with feed title, entry count, or error information.
    """
    if feed.bozo:
        error_msg = str(feed.bozo_exception)
        return FeedResult(url=url, success=False, error=error_msg)

    if not feed.entries:
        return FeedResult(url=url, success=False, error="No entries found")

    # feed.feed is a FeedParserDict containing feed metadata.
    # Type stubs incorrectly show it as list[FeedParserDict].
    title = feed.feed.get("title", "Unknown")  # type: ignore[union-attr]

    entries = []
    for entry in feed.entries:
        # Extract image from media:content, enclosures, or media:thumbnail
        image_url: str | None = None
        media = entry.get("media_content")
        if media and isinstance(media, list) and media:
            image_url = media[0].get("url")  # type: ignore[union-attr]
        if not image_url:
            enclosures = entry.get("enclosures")
            if enclosures and isinstance(enclosures, list):
                for enc in enclosures:
                    enc_type = enc.get("type", "") if isinstance(enc, dict) else ""
                    if isinstance(enc_type, str) and enc_type.startswith("image/"):
                        image_url = enc.get(
                            "href"
                        ) or enc.get(  # type: ignore[union-attr]
                            "url"
                        )  # type: ignore[union-attr]
                        break
        if not image_url:
            thumb = entry.get("media_thumbnail")
            if thumb and isinstance(thumb, list) and thumb:
                image_url = thumb[0].get("url")  # type: ignore[union-attr]

        entries.append(
            FeedEntry(
                url=entry.get("link", ""),  # type: ignore[arg-type]
                title=_strip_html_tags(entry.get("title")),  # type: ignore[arg-type]
                summary=_strip_html_tags(entry.get("summary")),  # type: ignore[arg-type]
                author=entry.get("author"),  # type: ignore[arg-type]
                published_at=entry.get("published"),  # type: ignore[arg-type]
                image_url=image_url,
            )
        )

    # Count valid articles (from current month or later)
    valid_count = sum(
        1 for e in entries if is_article_from_last_48_hours(e.published_at)
    )

    return FeedResult(
        url=url,
        title=title,
        entry_count=len(entries),
        valid_articles_count=valid_count,
        entries=entries,
        success=True,
    )


def extract_favicon(feed_url: str) -> str:
    """Construct favicon URL from feed URL domain using Google's service."""
    from helpers.url import get_base_url

    domain = get_base_url(feed_url)
    return f"https://www.google.com/s2/favicons?domain={domain}&sz=64"


def generate_rss_feed(
    articles: list[dict],
    site_title: str = "news48",
    site_url: str = "https://news48.io",
    site_description: str = "News from the last 48 hours",
) -> str:
    """Generate RSS 2.0 XML from a list of article dicts.

    Uses the standard library xml.etree.ElementTree.
    Includes:
    - Article title, link, description/summary
    - Published date (RFC 822)
    - Author
    - Categories (from comma-separated string)
    - Enclosure for image_url if present
    """
    from email.utils import formatdate
    from xml.etree.ElementTree import Element, SubElement, tostring

    rss = Element("rss", version="2.0")
    channel = SubElement(rss, "channel")

    SubElement(channel, "title").text = site_title
    SubElement(channel, "link").text = site_url
    SubElement(channel, "description").text = site_description
    SubElement(channel, "language").text = "en"

    for article in articles:
        item = SubElement(channel, "item")

        title = article.get("title") or "Untitled"
        SubElement(item, "title").text = title

        url = article.get("url", "")
        if url:
            SubElement(item, "link").text = url

        summary = article.get("summary") or ""
        if summary:
            SubElement(item, "description").text = summary

        author = article.get("author")
        if author:
            SubElement(item, "author").text = author

        published = article.get("published_at")
        if published:
            try:
                dt_obj = datetime.fromisoformat(published)
                timestamp = dt_obj.timestamp()
                SubElement(item, "pubDate").text = formatdate(timestamp)
            except (ValueError, TypeError):
                pass

        categories = article.get("categories")
        if categories:
            for cat in categories.split(","):
                cat = cat.strip()
                if cat:
                    SubElement(item, "category").text = cat

        image_url = article.get("image_url")
        if image_url:
            SubElement(
                item,
                "enclosure",
                url=image_url,
                type="image/jpeg",
                length="0",
            )

    xml_str = tostring(rss, encoding="unicode", xml_declaration=True)
    return xml_str
