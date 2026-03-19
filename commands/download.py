"""Download command - download the content of unparsed articles."""

import asyncio
import logging
from pathlib import Path

import typer
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
)

from config import Services
from database import get_empty_articles, update_article
from helpers import fetch_url_content, get_base_url, get_byparr_solution
from models import ByparrSolution

from ._common import console, require_db

logger = logging.getLogger(__name__)

MAX_CONCURRENT = 5
"""Default maximum number of concurrent download tasks."""


async def _get_domain_lock(
    domain: str,
    domain_locks: dict[str, asyncio.Lock],
    meta_lock: asyncio.Lock,
) -> asyncio.Lock:
    """Return the per-domain lock, creating it if needed.

    Args:
        domain: The domain key.
        domain_locks: Shared map of domain → Lock.
        meta_lock: Lock that protects *domain_locks* itself.

    Returns:
        The asyncio.Lock for *domain*.
    """
    async with meta_lock:
        if domain not in domain_locks:
            domain_locks[domain] = asyncio.Lock()
        return domain_locks[domain]


async def _ensure_solution(
    domain: str,
    solutions: dict[str, ByparrSolution],
    domain_lock: asyncio.Lock,
    stale: ByparrSolution | None = None,
) -> ByparrSolution:
    """Get or refresh the bypass solution for *domain*.

    If *stale* is provided and the cached solution is still the
    same object, a fresh one is fetched.  Otherwise the existing
    (possibly already-refreshed) cached solution is returned.

    Args:
        domain: The website domain.
        solutions: Shared domain → solution cache.
        domain_lock: Per-domain lock.
        stale: The solution that was used when the failure
            occurred, or ``None`` for the initial fetch.

    Returns:
        A (possibly fresh) ByparrSolution.
    """
    async with domain_lock:
        cached = solutions.get(domain)
        need_refresh = cached is None or (
            stale is not None and cached is stale
        )
        if need_refresh:
            solutions[domain] = await get_byparr_solution(
                target_url=f"https://{domain}/",
                bypass_api_url=Services.byparr,
            )
        return solutions[domain]


async def _download_article(
    article: dict,
    solutions: dict[str, ByparrSolution],
    domain_locks: dict[str, asyncio.Lock],
    meta_lock: asyncio.Lock,
    semaphore: asyncio.Semaphore,
    db_path: Path,
    progress: Progress,
    task_id: TaskID,
) -> bool:
    """Download a single article's content.

    Fetches the bypass solution for the article's domain
    (caching it for reuse), downloads the page HTML, and
    stores it in the database. Fails fast on any error.

    Args:
        article: Article dict (must contain ``url`` and ``id``).
        solutions: Shared domain → ByparrSolution cache.
        domain_locks: Per-domain locks for solution refresh.
        meta_lock: Lock protecting *domain_locks* dict.
        semaphore: Concurrency limiter.
        db_path: Path to the SQLite database file.
        progress: Rich progress bar instance.
        task_id: Progress bar task ID to advance.

    Returns:
        ``True`` if downloaded successfully, ``False`` otherwise.
    """
    async with semaphore:
        url = article["url"]
        domain = get_base_url(url=url)
        domain_lock = await _get_domain_lock(
            domain,
            domain_locks,
            meta_lock,
        )

        try:
            solution = await _ensure_solution(
                domain,
                solutions,
                domain_lock,
            )
        except Exception as e:
            logger.exception("Failed to get solution for %s", domain)
            console.print(f"[red]Solution failed: {domain} - {e}[/red]")
            progress.advance(task_id)
            return False

        try:
            content = await fetch_url_content(
                url=url,
                solution=solution,
            )
            update_article(
                db_path,
                article["id"],
                content=content,
            )
            progress.advance(task_id)
            return True

        except Exception as e:
            logger.exception("Failed to download %s", url)
            console.print(f"[red]Failed: {url} - {e}[/red]")
            progress.advance(task_id)
            return False


async def _download(limit: int, delay: float) -> None:
    """Download content for articles not yet downloaded.

    Args:
        limit: Maximum number of articles to download.
        delay: Delay between download starts in seconds.
    """
    db_path = require_db()

    articles = get_empty_articles(db_path, limit)
    if not articles:
        console.print(
            "[yellow]No unparsed articles found[/yellow]",
        )
        return

    console.print(f"Found {len(articles)} unparsed articles")

    solutions: dict[str, ByparrSolution] = {}
    domain_locks: dict[str, asyncio.Lock] = {}
    meta_lock = asyncio.Lock()
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    with Progress(
        SpinnerColumn(),
        TextColumn(
            "[progress.description]{task.description}",
        ),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task_id = progress.add_task(
            "Downloading",
            total=len(articles),
        )

        async def _throttled(
            idx: int,
            article: dict,
        ) -> bool:
            if idx > 0:
                await asyncio.sleep(delay * idx)
            return await _download_article(
                article=article,
                solutions=solutions,
                domain_locks=domain_locks,
                meta_lock=meta_lock,
                semaphore=semaphore,
                db_path=db_path,
                progress=progress,
                task_id=task_id,
            )

        results = await asyncio.gather(
            *(_throttled(i, a) for i, a in enumerate(articles))
        )

    downloaded = sum(1 for r in results if r)
    failed = sum(1 for r in results if not r)

    console.print(
        f"[green]Downloaded: {downloaded}[/green] | "
        f"[red]Failed: {failed}[/red]"
    )


def download(
    limit: int = typer.Option(
        10,
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
) -> None:
    """Download content of unparsed articles.

    Articles must be fetched first using the 'fetch' command.
    This command processes articles whose content has not been
    downloaded yet.

    Args:
        limit: Maximum number of articles to download.
        delay: Delay between download starts in seconds.
    """
    asyncio.run(_download(limit, delay))
