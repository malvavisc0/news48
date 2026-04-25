"""Agent tool for fetching webpage content using bypass solutions."""

import asyncio
import logging
from typing import Any

from markdownify import markdownify

from news48.core.config import Services
from news48.core.helpers.bypass import (
    fetch_url_content,
    get_byparr_solution,
    strip_html_noise,
)
from news48.core.helpers.security import validate_url_not_private
from news48.core.helpers.url import get_base_url
from news48.core.models import ByparrSolution

from ._helpers import _safe_json

logger = logging.getLogger(__name__)


async def fetch_webpage_content(
    reason: str, urls: list[str], markdown: bool = True
) -> str:
    """Fetch webpage content from URLs using anti-bot bypass solutions.

    ## When to Use
    Use this tool when you need to extract content from web pages that may be
    protected by anti-bot mechanisms (e.g., Cloudflare, CAPTCHAs,
    rate limiting).
    For general web search results, prefer `perform_web_search` instead.

    ## Why to Use
    - Websites with bot protection block regular HTTP requests
    - Bypass solutions route requests through specialized proxies
    - Converts HTML to markdown for easier parsing by LLMs

    ## Parameters
    - `reason` (str): Why these URLs need to be fetched (helps with debugging)
    - `urls` (list[str]): List of webpage URLs to fetch
    - `markdown` (bool): Convert HTML to markdown (default: True)

    ## Returns
    JSON with:
    - `result.results`: List of {url, content, success} for each fetch
    - `result.errors`: List of {url, error} for failed fetches
    - `error`: Empty on success, summary message if any fetches failed

    ## Example
    ```python
    result = await fetch_webpage_content(
        reason="Research product reviews for comparison",
        urls=["https://example.com/review1", "https://example.com/review2"]
    )
    ```
    """
    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    # Cache bypass solutions by domain
    solutions: dict[str, ByparrSolution] = {}
    domain_locks: dict[str, asyncio.Lock] = {}
    meta_lock = asyncio.Lock()

    async def get_solution(domain: str) -> ByparrSolution:
        """Get or create bypass solution for domain."""
        async with meta_lock:
            if domain not in domain_locks:
                domain_locks[domain] = asyncio.Lock()
        async with domain_locks[domain]:
            if domain not in solutions:
                solutions[domain] = await get_byparr_solution(
                    target_url=f"https://{domain}/",
                    bypass_api_url=Services.byparr(),
                )
            return solutions[domain]

    async def fetch_one(url: str) -> dict[str, Any]:
        """Fetch a single URL and return result dict."""
        try:
            # SSRF prevention: validate URL doesn't target private IPs
            validate_url_not_private(url)
            domain = get_base_url(url=url)
            solution = await get_solution(domain)
            content = await fetch_url_content(url=url, solution=solution)
            if markdown:
                content = markdownify(content) or ""
            else:
                content = strip_html_noise(content)

            return {"url": url, "content": content, "success": True}
        except Exception as e:
            return {"url": url, "error": str(e), "success": False}

    async def fetch_all() -> list[dict[str, Any]]:
        """Fetch all URLs concurrently while preserving input order."""
        return await asyncio.gather(*(fetch_one(url) for url in urls))

    raw_results = await fetch_all()

    # Process results
    for result in raw_results:
        if result.get("success"):
            results.append(result)
        else:
            errors.append(
                {
                    "url": result.get("url", ""),
                    "error": result.get("error", "Unknown error"),
                }
            )

    success = len(results) > 0
    error = "" if success else f"Failed to fetch {len(errors)} of {len(urls)} URL(s)"

    return _safe_json(
        {
            "result": {
                "results": results,
                "errors": errors,
                "requested": len(urls),
                "succeeded": len(results),
                "failed": len(errors),
            },
            "error": error,
        }
    )
