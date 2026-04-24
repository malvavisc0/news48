"""Fetch command - fetch and parse RSS/Atom feeds from URLs stored."""

import asyncio

import typer

from news48.core.database import get_all_feeds
from news48.core.helpers import get_fetch_summary

from ._common import DEFAULT_DELAY, emit_error, emit_json, require_db, status_msg


async def _fetch(delay: float, feed_domain: str | None = None) -> dict:
    """Async entry point: load URLs from database, fetch feeds.

    Args:
        delay: Delay between requests in seconds.
        feed_domain: Optional domain to filter feeds by.

    Returns:
        A dict with fetch results.
    """
    require_db()

    feeds = get_all_feeds(feed_domain=feed_domain)
    if not feeds:
        return {
            "feed_filter": feed_domain,
            "feeds_fetched": 0,
            "entries": 0,
            "valid": 0,
            "success_rate": 0.0,
            "successful": [],
            "failed": [],
        }

    urls = [feed["url"] for feed in feeds]
    status_msg(f"Fetching {len(urls)} feeds...")

    summary = await get_fetch_summary(
        urls,
        delay,
        track_db=True,
        on_feed_done=lambda _: None,
    )

    total_entries = sum(r.entry_count for r in summary.successful)
    total_valid = sum(r.valid_articles_count for r in summary.successful)
    total_feeds = len(summary.successful) + len(summary.failed)
    success_rate = (
        (len(summary.successful) / total_feeds * 100) if total_feeds > 0 else 0.0
    )

    return {
        "feed_filter": feed_domain,
        "feeds_fetched": len(summary.successful),
        "entries": total_entries,
        "valid": total_valid,
        "success_rate": round(success_rate, 1),
        "successful": [
            {
                "title": r.title or "Unknown",
                "url": r.url,
                "entries": r.entry_count,
                "valid": r.valid_articles_count,
            }
            for r in summary.successful
        ],
        "failed": [
            {"url": r.url, "error": r.error or "Unknown error"} for r in summary.failed
        ],
    }


def fetch(
    delay: float = typer.Option(
        DEFAULT_DELAY,
        "--delay",
        "-d",
        help="Delay between requests in seconds",
    ),
    feed: str = typer.Option(None, "--feed", help="Filter by feed domain"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Fetch RSS/Atom feeds and store new articles in the database.

    Feeds must be seeded first using 'news48 seed'. After fetching,
    run 'news48 download' to get full article content, then
    'news48 parse' to extract structured data.

    Examples:
        news48 fetch
        news48 fetch --feed reuters.com --delay 1.0
        news48 fetch --json
    """
    try:
        data = asyncio.run(_fetch(delay, feed_domain=feed))
    except SystemExit:
        raise
    except Exception as e:
        emit_error(str(e), as_json=output_json)
    if output_json:
        emit_json(data)
    else:
        print(
            f"Fetched {data['feeds_fetched']} feeds, "
            f"{data['entries']} entries, "
            f"{data['valid']} valid"
        )
        print(f"Success rate: {data['success_rate']}%")
        if data["failed"]:
            print(f"Failed: {len(data['failed'])} feeds")
            for f in data["failed"]:
                print(f"  - {f['url']}: {f['error']}")
