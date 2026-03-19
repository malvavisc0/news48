"""Feed fetching and date utilities."""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, List

import dateparser
import feedparser

from database import (
    complete_run,
    create_run,
    fail_run,
    get_feed_by_url,
    insert_articles,
    update_feed_metadata,
)
from models import FeedEntry, FeedResult, FeedSummary


def is_article_from_current_month(published_at: str | None) -> bool:
    """Check if an article was published in the current month or later.

    Args:
        published_at: The publication date string from the feed entry.
                    Can be in various formats (ISO 8601, RFC 2822, etc.)

    Returns:
        True if the article is from the current month or later,
        False if the article is older than the current month or if
        published_at is None/empty.
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
        current_year = now.year
        current_month = now.month

        # Compare year and month
        if article_date.year > current_year:
            return True
        if article_date.year < current_year:
            return False
        # Same year - compare month
        return article_date.month >= current_month
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


def load_urls(filepath: str) -> List[str]:
    """Load URLs from a file, one per line.

    Args:
        filepath: Path to the file containing URLs.

    Returns:
        A list of URLs, one per line, with whitespace stripped.
    """
    with open(filepath, encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


async def get_fetch_summary(
    urls: List[str],
    delay: float,
    db_path: Path | None = None,
    on_feed_done: Callable[[FeedResult], None] | None = None,
) -> FeedSummary:
    """Fetch multiple feeds and return a summary of results.

    Args:
        urls: List of feed URLs to fetch.
        delay: Delay between requests in seconds.
        db_path: Optional path to SQLite database for tracking.
        on_feed_done: Optional callback invoked after each feed is
            fetched, receiving the FeedResult.

    Returns:
        A FeedSummary containing successful and failed feed results.
    """
    summary = FeedSummary()
    run_id = None

    if db_path:
        run_id = create_run(db_path)

    try:
        for i, url in enumerate(urls):
            if i > 0:
                await asyncio.sleep(delay)
            result = await _fetch_feed(url)
            summary.add_result(result)
            if on_feed_done:
                on_feed_done(result)

            if db_path and run_id and result.success:
                feed = get_feed_by_url(db_path, url)
                if feed:
                    update_feed_metadata(
                        db_path, feed["id"], result.title or "Unknown"
                    )
                    # Filter: only articles from current month or later
                    articles = [
                        entry.model_dump()
                        for entry in result.entries
                        if is_article_from_current_month(entry.published_at)
                    ]
                    # Each function manages its own connection
                    insert_articles(db_path, run_id, feed["id"], articles)

        if db_path and run_id:
            complete_run(
                db_path,
                run_id,
                len(urls),
                sum(r.valid_articles_count for r in summary.successful),
            )
    except Exception:
        if db_path and run_id:
            fail_run(db_path, run_id)
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
        entries.append(
            FeedEntry(
                url=entry.get("link", ""),  # type: ignore[arg-type]
                title=entry.get("title"),  # type: ignore[arg-type]
                summary=entry.get("summary"),  # type: ignore[arg-type]
                author=entry.get("author"),  # type: ignore[arg-type]
                published_at=entry.get("published"),  # type: ignore[arg-type]
            )
        )

    # Count valid articles (from current month or later)
    valid_count = sum(
        1 for e in entries if is_article_from_current_month(e.published_at)
    )

    return FeedResult(
        url=url,
        title=title,
        entry_count=len(entries),
        valid_articles_count=valid_count,
        entries=entries,
        success=True,
    )
