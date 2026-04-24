"""Fact-check agent for autonomous article verification."""

import asyncio
import logging
import os
import tempfile
from os import getenv

from llama_index.core.agent.workflow import FunctionAgent
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
    """Run the fact-checker agent for one article already claimed in the database."""
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
        await run_agent(lambda: get_agent({}), task)

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
                logger.debug("Failed to delete temp fact-check file: %s", content_path)


def _record_failure(article_id: int, error: str) -> None:
    """Record a fact-check failure as unverifiable to prevent infinite retries."""
    try:
        update_article_fact_check(
            article_id,
            status="unverifiable",
            result=f"Fact-check agent failed: {error}",
            force=True,
        )
    except Exception:
        logger.warning("Failed to record fact-check failure for article %s", article_id)


async def run_cycle(limit: int = 10) -> dict:
    """Run one fact-check cycle by claiming fact-unchecked articles."""
    articles, total = get_articles_paginated(limit=limit, status="fact-unchecked")
    if not articles:
        return {"checked": 0, "results": []}

    owner = f"fact_checker:{os.getpid()}"

    # Claim articles to prevent duplicate work across concurrent workers
    candidate_ids = [int(a["id"]) for a in articles]
    claimed_ids = claim_articles_for_processing(candidate_ids, "fact_check", owner)
    claimed_articles = [a for a in articles if int(a["id"]) in claimed_ids]

    if not claimed_articles:
        return {"checked": 0, "results": []}

    # Process with concurrency limit (lower than parser since fact-checking is heavier)
    sem = asyncio.Semaphore(3)

    async def _check_one(article: dict) -> dict:
        async with sem:
            return await _fact_check_article(article, owner)

    results = await asyncio.gather(*(_check_one(a) for a in claimed_articles))

    processed = len(results)
    return {"checked": processed, "results": results}


def get_agent(task_context: dict | None = None) -> FunctionAgent:
    """Create and return the Fact-Check Agent."""
    api_base = getenv("API_BASE", "")
    api_key = getenv("API_KEY", "")
    model = getenv("MODEL", "")
    if not api_base:
        raise ValueError("Missing API_BASE env.")

    from .tools import (
        fetch_webpage_content,
        perform_web_search,
        read_file,
        run_shell_command,
        save_lesson,
    )

    ctx = task_context or {}

    return FunctionAgent(
        name="FactChecker",
        description=(
            "Fact-checks articles by searching for evidence and " "recording verdicts."
        ),
        tools=[
            perform_web_search,
            fetch_webpage_content,
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
