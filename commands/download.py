"""Download command - download the content of unparsed articles."""

import asyncio
import logging
import os
from pathlib import Path

import typer
from html_to_markdown import convert as html_to_markdown

from config import Services
from database import (
    claim_articles_for_processing,
    clear_article_processing_claim,
    get_article_by_id,
    get_download_failed_articles,
    get_empty_articles,
    mark_article_download_failed,
    reset_article_download,
    update_article,
)
from helpers import (
    fetch_url_content,
    get_base_url,
    get_byparr_solution,
    strip_html_noise,
)
from helpers.url import extract_og_image
from models import ByparrSolution

from ._common import emit_error, emit_json, require_db

logger = logging.getLogger(__name__)

MAX_CONCURRENT = 15
"""Default maximum number of concurrent download tasks."""

MAX_RETRIES = 3
"""Maximum number of retry attempts for failed downloads."""

RETRY_DELAY_BASE = 2.0
"""Base delay in seconds for exponential backoff."""


async def _get_domain_semaphore(
    domain: str,
    domain_sems: dict[str, asyncio.Semaphore],
    meta_lock: asyncio.Lock,
) -> asyncio.Semaphore:
    """Return the per-domain semaphore, creating it if needed."""
    async with meta_lock:
        if domain not in domain_sems:
            domain_sems[domain] = asyncio.Semaphore(4)
        return domain_sems[domain]


async def _ensure_solution(
    domain: str,
    solutions: dict[str, ByparrSolution],
    domain_sem: asyncio.Semaphore,
    stale: ByparrSolution | None = None,
) -> ByparrSolution:
    """Get or refresh the bypass solution for *domain*."""
    async with domain_sem:
        cached = solutions.get(domain)
        need_refresh = cached is None or (
            stale is not None and cached is stale
        )
        if need_refresh:
            solutions[domain] = await get_byparr_solution(
                target_url=f"https://{domain}/",
                bypass_api_url=Services.byparr(),
            )
        return solutions[domain]


async def _download_article(
    article: dict,
    solutions: dict[str, ByparrSolution],
    domain_sems: dict[str, asyncio.Semaphore],
    meta_lock: asyncio.Lock,
    semaphore: asyncio.Semaphore,
    db_path: Path,
    claim_owner: str,
) -> bool:
    """Download a single article with retry logic."""
    async with semaphore:
        url = article["url"]
        domain = get_base_url(url=url)
        domain_sem = await _get_domain_semaphore(
            domain,
            domain_sems,
            meta_lock,
        )

        try:
            try:
                solution = await _ensure_solution(
                    domain,
                    solutions,
                    domain_sem,
                )
            except Exception as e:
                logger.exception("Failed to get solution for %s", domain)
                mark_article_download_failed(db_path, article["id"], str(e))
                return False

            last_error = None
            for attempt in range(MAX_RETRIES + 1):
                try:
                    raw_html = await fetch_url_content(
                        url=url,
                        solution=solution,
                    )
                    image_url = extract_og_image(raw_html)
                    cleaned_html = strip_html_noise(raw_html)
                    content = html_to_markdown(cleaned_html)["content"] or ""
                    update_article(
                        db_path,
                        article["id"],
                        content=content,
                        image_url=image_url,
                    )
                    return True
                except Exception as e:
                    last_error = e
                    logger.warning(
                        "Attempt %d/%d failed for %s: %s",
                        attempt + 1,
                        MAX_RETRIES + 1,
                        url,
                        str(e),
                    )
                    if attempt < MAX_RETRIES:
                        delay = RETRY_DELAY_BASE * (2**attempt)
                        logger.info(
                            f"Retry {attempt + 1}/{MAX_RETRIES} "
                            f"for {url} in {delay:.1f}s"
                        )
                        await asyncio.sleep(delay)

            logger.exception(
                "Failed to download %s after %d attempts",
                url,
                MAX_RETRIES + 1,
            )
            logger.info(f"Failed: {url} - {last_error}")
            mark_article_download_failed(
                db_path, article["id"], str(last_error)
            )
            return False
        finally:
            clear_article_processing_claim(
                db_path,
                article["id"],
                owner=claim_owner,
            )


async def _download(
    limit: int,
    delay: float,
    feed_domain: str | None = None,
    retry: bool = False,
    article_id: int | None = None,
    force: bool = False,
) -> dict:
    """Download content for articles not yet downloaded.

    Args:
        limit: Maximum number of articles to download.
        delay: Delay between download starts in seconds.
        feed_domain: Optional domain to filter by.
        retry: If True, retry failed downloads.
        article_id: Optional specific article ID to download.

    Returns:
        A dict with download results.
    """
    db_path = require_db()
    claim_owner = f"download:{os.getpid()}"

    if article_id is not None:
        article = get_article_by_id(db_path, article_id)
        if not article:
            return {"error": f"Article not found: {article_id}"}
        if article.get("content") and not force:
            return {
                "error": (
                    f"Article {article_id} already has content. "
                    "Use --force to download it again."
                )
            }
        if force or retry or article.get("download_failed"):
            reset_article_download(db_path, article_id)
        claimed = claim_articles_for_processing(
            db_path,
            [article_id],
            "download",
            claim_owner,
            force=force,
        )
        if article_id not in claimed:
            return {
                "error": (
                    f"Article {article_id} is already being processed. "
                    "Use --force to override the active claim."
                )
            }
        articles = [article]
        logger.info(f"Downloading article {article_id}")
    elif retry:
        candidates = get_download_failed_articles(
            db_path, limit, feed_domain=feed_domain
        )
        if not candidates:
            logger.info("No failed downloads found to retry")
            return {
                "feed_filter": feed_domain,
                "downloaded": 0,
                "failed": 0,
                "total": 0,
                "retry": True,
            }
        claimed = set(
            claim_articles_for_processing(
                db_path,
                [article["id"] for article in candidates],
                "download",
                claim_owner,
                force=force,
            )
        )
        articles = [
            article for article in candidates if article["id"] in claimed
        ]
        if not articles:
            logger.info("All failed downloads are already being processed")
            return {
                "feed_filter": feed_domain,
                "downloaded": 0,
                "failed": 0,
                "total": 0,
                "retry": True,
            }
        logger.info(f"Found {len(articles)} failed downloads to retry")
    else:
        candidates = get_empty_articles(
            db_path, limit, feed_domain=feed_domain
        )
        if not candidates:
            logger.info("No articles need downloading")
            return {
                "feed_filter": feed_domain,
                "downloaded": 0,
                "failed": 0,
                "total": 0,
                "retry": False,
            }
        claimed = set(
            claim_articles_for_processing(
                db_path,
                [article["id"] for article in candidates],
                "download",
                claim_owner,
                force=force,
            )
        )
        articles = [
            article for article in candidates if article["id"] in claimed
        ]
        if not articles:
            logger.info("All candidate downloads are already being processed")
            return {
                "feed_filter": feed_domain,
                "downloaded": 0,
                "failed": 0,
                "total": 0,
                "retry": False,
            }
        logger.info(f"Found {len(articles)} articles to download")

    solutions: dict[str, ByparrSolution] = {}
    domain_sems: dict[str, asyncio.Semaphore] = {}
    meta_lock = asyncio.Lock()
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    async def _throttled(article: dict) -> bool:
        return await _download_article(
            article=article,
            solutions=solutions,
            domain_sems=domain_sems,
            meta_lock=meta_lock,
            semaphore=semaphore,
            db_path=db_path,
            claim_owner=claim_owner,
        )

    results = await asyncio.gather(*(_throttled(a) for a in articles))

    downloaded = sum(1 for r in results if r)
    failed = sum(1 for r in results if not r)

    return {
        "feed_filter": feed_domain,
        "downloaded": downloaded,
        "failed": failed,
        "total": len(articles),
        "retry": retry,
    }


def download(
    limit: int = typer.Option(
        50,
        "--limit",
        "-l",
        help="Maximum number of articles to download",
    ),
    delay: float = typer.Option(
        1.0,
        "--delay",
        "-d",
        help="Delay between download starts in seconds",
    ),
    feed: str = typer.Option(None, "--feed", help="Filter by feed domain"),
    retry: bool = typer.Option(
        False, "--retry", "-r", help="Retry failed downloads"
    ),
    article: int = typer.Option(
        None, "--article", help="Download a specific article by ID"
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Override active claims or re-download a specific article",
    ),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Download content of unparsed articles.

    Articles must be fetched first using the 'fetch' command.
    This command processes articles whose content has not been
    downloaded yet. Use --article to target a specific article.

    Args:
        limit: Maximum number of articles to download.
        delay: Delay between download starts in seconds.
        feed: Optional domain to filter by.
        retry: Retry articles that previously failed downloading.
        article: Download a specific article by ID.
        output_json: Output as JSON instead of human-readable text.
    """
    try:
        data = asyncio.run(
            _download(
                limit,
                delay,
                feed_domain=feed,
                retry=retry,
                article_id=article,
                force=force,
            )
        )
    except SystemExit:
        raise
    except Exception as e:
        emit_error(str(e), as_json=output_json)
        return
    if "error" in data:
        emit_error(data["error"], as_json=output_json)
        return
    if output_json:
        emit_json(data)
    else:
        print(
            f"Downloaded {data['downloaded']} of {data['total']} "
            f"articles, {data['failed']} failed"
        )
