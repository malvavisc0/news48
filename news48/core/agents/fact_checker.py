"""Fact-check agent for autonomous article verification."""

import asyncio
import json
import logging
import os
import tempfile
from os import getenv
from typing import Literal

from llama_index.core.agent.workflow import FunctionAgent
from llama_index.core.tools import FunctionTool
from llama_index.llms.openai_like import OpenAILike

from news48.core.database import (
    claim_articles_for_processing,
    clear_article_processing_claim,
    get_article_by_id,
    get_articles_paginated,
    update_article_fact_check,
)

from ._run import run_agent
from .skills import compose_agent_instructions

logger = logging.getLogger(__name__)


def _write_claims_file(article_id: int, content: str) -> str:
    """Write article content to a temp file for the fact-checker agent."""
    tmp = tempfile.NamedTemporaryFile(
        mode="w", delete=False, suffix=".txt", prefix=f"fc-{article_id}-"
    )
    tmp.write(content)
    tmp.close()
    return tmp.name


def _build_fact_check_task(article: dict, content_path: str) -> str:
    """Build the fact-checker task payload for a single article."""
    parts = [
        "Fact-check the following article. Record per-claim verdicts.",
        "--------------------------------------",
        f"Article ID: {article['id']}",
        f"Title: {article['title']}",
        f"URL: {article['url']}",
        "⚠️ IMPORTANT: Do NOT use this URL as a source. "
        "You must find independent external sources to verify claims.",
        f"Content file path: {content_path}",
    ]

    # Include some metadata if available to help the agent assess claims
    if article.get("categories"):
        parts.append(f"Categories: {article['categories']}")
    if article.get("tags"):
        parts.append(f"Tags: {article['tags']}")
    if article.get("sentiment"):
        parts.append(f"Sentiment: {article['sentiment']}")

    return "\n".join(parts) + "\n"


async def _fact_check_article(article: dict, owner: str) -> dict:
    """Run the fact-checker agent for one article already claimed."""
    # Fetch full article content (get_articles_paginated doesn't include it)
    full_article = get_article_by_id(int(article["id"]))
    if not full_article:
        return {
            "id": article["id"],
            "title": article.get("title"),
            "url": article.get("url"),
            "success": False,
            "error": "Article not found",
        }

    content = full_article.get("content") or ""
    if not content.strip():
        error = "Article has no content to fact-check"
        _record_failure(article["id"], error)
        return {
            "id": article["id"],
            "title": article.get("title"),
            "url": article.get("url"),
            "success": False,
            "error": error,
        }

    content_path = None
    try:
        content_path = _write_claims_file(article["id"], content)
        task = _build_fact_check_task(full_article, content_path)
        # Pass article URL in context so instructions can reference it
        # for source-exclusion (preventing circular verification).
        ctx = {"article_url": full_article.get("url", "")}
        await run_agent(lambda: get_agent(ctx), task)

        # Check if fact_check_status was updated
        updated = get_article_by_id(article["id"])
        if updated and updated.get("fact_check_status"):
            return {
                "id": article["id"],
                "title": article.get("title"),
                "url": article.get("url"),
                "success": True,
            }

        error = "Agent did not produce a verdict"
        _record_failure(article["id"], error)
        return {
            "id": article["id"],
            "title": article.get("title"),
            "url": article.get("url"),
            "success": False,
            "error": error,
        }
    except Exception as exc:
        error = str(exc)
        _record_failure(article["id"], error)
        return {
            "id": article["id"],
            "title": article.get("title"),
            "url": article.get("url"),
            "success": False,
            "error": error,
        }
    finally:
        clear_article_processing_claim(article["id"], owner=owner)
        if content_path:
            try:
                os.unlink(content_path)
            except OSError:
                logger.debug(
                    "Failed to delete temp fact-check file: %s", content_path
                )


def _record_failure(article_id: int, error: str) -> None:
    """Record a fact-check failure as error so it can be retried later.

    Using a distinct ``"fact_check_error"`` status allows the article to
    be picked up again in a future fact-check cycle, unlike ``"unverifiable"``
    which is permanent until the data purge.
    """
    try:
        update_article_fact_check(
            article_id,
            status="fact_check_error",
            result=f"Fact-check agent failed: {error}",
            force=True,
        )
    except Exception:
        logger.warning(
            "Failed to record fact-check failure for article %s", article_id
        )


async def run_cycle(limit: int = 10) -> dict:
    """Run one fact-check cycle by claiming fact-unchecked articles.

    Also includes articles with ``fact_check_error`` status so they
    can be retried after a transient failure.
    """
    articles_unchecked, _ = get_articles_paginated(
        limit=limit, status="fact-unchecked"
    )
    articles_error, _ = get_articles_paginated(
        limit=limit, status="fact-check-error"
    )

    # Merge and deduplicate by article ID
    seen = set()
    articles = []
    for a in articles_unchecked + articles_error:
        aid = int(a["id"])
        if aid not in seen:
            seen.add(aid)
            articles.append(a)

    # Respect the limit
    articles = articles[:limit]

    if not articles:
        return {"checked": 0, "results": []}

    owner = f"fact_checker:{os.getpid()}"

    # Claim articles to prevent duplicate work across concurrent workers
    candidate_ids = [int(a["id"]) for a in articles]
    claimed_ids = claim_articles_for_processing(
        candidate_ids, "fact_check", owner
    )
    claimed_articles = [a for a in articles if int(a["id"]) in claimed_ids]

    if not claimed_articles:
        return {"checked": 0, "results": []}

    # Process with concurrency limit (lower than parser)
    sem = asyncio.Semaphore(3)

    async def _check_one(article: dict) -> dict:
        async with sem:
            return await _fact_check_article(article, owner)

    results = await asyncio.gather(*(_check_one(a) for a in claimed_articles))

    processed = len(results)
    return {"checked": processed, "results": results}


def _make_filtered_search(article_url: str):
    """Return a perform_web_search wrapper that strips the article's own URL."""
    from .tools import perform_web_search as _raw_search
    from .tools._helpers import urls_match

    def perform_web_search(
        reason: str,
        query: str,
        category: Literal[
            "general", "files", "news", "videos", "images"
        ] = "general",
        time_range: Literal["", "day", "week", "month", "year"] = "",
        pages: int = 3,
    ) -> str:
        """Search the web via SearXNG (article URL auto-excluded)."""
        raw = _raw_search(reason, query, category, time_range, pages)
        if not article_url:
            return raw

        data = json.loads(raw)
        findings = data.get("result", {}).get("findings", [])
        before = len(findings)
        findings = [
            f
            for f in findings
            if not urls_match(f.get("url", ""), article_url)
        ]
        removed = before - len(findings)
        data["result"]["findings"] = findings
        data["result"]["count"] = len(findings)
        if removed:
            data["result"]["excluded_article_url"] = removed
        return json.dumps(data, indent=2, ensure_ascii=True)

    return FunctionTool.from_defaults(fn=perform_web_search)


def _make_filtered_fetch(article_url: str):
    """Return a fetch_webpage_content wrapper that blocks the article's own URL."""
    from .tools import fetch_webpage_content as _raw_fetch
    from .tools._helpers import urls_match

    _BLOCK_MSG = "Blocked: this is the article being fact-checked (circular verification)."

    async def fetch_webpage_content(
        reason: str, urls: list[str], markdown: bool = True
    ) -> str:
        """Fetch webpage content (article URL auto-blocked)."""
        blocked: list[str] = []
        if article_url:
            blocked = [u for u in urls if urls_match(u, article_url)]
            urls = [u for u in urls if not urls_match(u, article_url)]

        if not urls:
            # Every URL was blocked — return immediately
            return json.dumps(
                {
                    "result": {
                        "results": [],
                        "errors": [
                            {"url": u, "error": _BLOCK_MSG} for u in blocked
                        ],
                        "requested": len(blocked),
                        "succeeded": 0,
                        "failed": len(blocked),
                    },
                    "error": "All URLs blocked: cannot fetch the article being fact-checked.",
                }
            )

        raw = await _raw_fetch(reason, urls, markdown)
        if not blocked:
            return raw

        # Merge blocked-URL errors into the upstream response
        data = json.loads(raw)
        for u in blocked:
            data["result"].setdefault("errors", []).append(
                {"url": u, "error": _BLOCK_MSG}
            )
        data["result"]["failed"] = data["result"].get("failed", 0) + len(
            blocked
        )
        data["result"]["requested"] = data["result"].get("requested", 0) + len(
            blocked
        )
        return json.dumps(data, indent=2, ensure_ascii=True)

    return FunctionTool.from_defaults(async_fn=fetch_webpage_content)


def get_agent(task_context: dict | None = None) -> FunctionAgent:
    """Create and return the Fact-Check Agent."""
    api_base = getenv("API_BASE", "")
    api_key = getenv("API_KEY", "")
    model = getenv("MODEL", "")
    if not api_base:
        raise ValueError("Missing API_BASE env.")

    from .tools import (
        create_plan,
        read_file,
        run_shell_command,
        save_lesson,
        update_plan,
    )

    ctx = task_context or {}
    article_url = ctx.get("article_url", "")

    return FunctionAgent(
        name="FactChecker",
        description=(
            "Fact-checks articles by searching for evidence and "
            "recording verdicts."
        ),
        tools=[
            _make_filtered_search(article_url),
            _make_filtered_fetch(article_url),
            create_plan,
            update_plan,
            run_shell_command,
            read_file,
            save_lesson,
        ],
        llm=OpenAILike(
            model=model,
            api_base=api_base,
            api_key=api_key,
            is_chat_model=True,
            is_function_calling_model=True,
        ),
        system_prompt=compose_agent_instructions("fact_checker", ctx),
        verbose=False,
        streaming=True,
    )


async def run(task: str, task_context: dict | None = None):
    """Run the Fact-Check Agent with a task prompt."""
    return await run_agent(lambda: get_agent(task_context), task)


async def run_autonomous(task: str = ""):
    """Run the autonomous fact-check schedule entry."""
    return await run_cycle(limit=10)
