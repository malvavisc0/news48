"""Parser agent for autonomous article parsing."""

import asyncio
import logging
import os
import tempfile
from os import getenv

from llama_index.core.agent.workflow import FunctionAgent
from llama_index.llms.openai_like import OpenAILike

from agents._run import run_agent
from agents.skills import compose_agent_instructions
from database import (
    claim_articles_for_processing,
    clear_article_processing_claim,
    get_article_by_id,
    get_unparsed_articles,
    init_database,
    mark_article_parse_failed,
)

logger = logging.getLogger(__name__)


def _get_temp_file_path(content: str) -> str:
    """Create a temp HTML file for parser consumption."""
    tmp = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt")
    tmp.write(content)
    tmp.close()
    return tmp.name


def _build_parse_task(article: dict, tmp_path: str) -> str:
    """Build the parser task payload for a single claimed article."""
    return (
        f"\nParse the following article.\n"
        f"--------------------------------------\n"
        f"Article ID: {article['id']}\n"
        f"Title: {article['title']}\n"
        f"HTML file path: {tmp_path}\n"
        f"URL: {article['url']}\n"
        f"--------------------------------------\n"
    )


async def _parse_claimed_article(article: dict, owner: str) -> dict:
    """Run the parser agent for one article already claimed in the database."""
    from commands._common import require_db

    db_path = require_db()
    tmp_path = None
    try:
        tmp_path = _get_temp_file_path(article.get("content") or "")
        task = _build_parse_task(article, tmp_path)
        await run_agent(lambda: get_agent({}), task)

        updated = get_article_by_id(db_path, int(article["id"]))
        if updated and updated.get("parsed_at"):
            return {
                "id": int(article["id"]),
                "title": updated.get("title") or article.get("title"),
                "url": article.get("url"),
                "success": True,
            }

        # If the agent already reported a specific failure via
        # `articles fail`, preserve that error instead of overwriting.
        if updated and updated.get("parse_failed"):
            return {
                "id": int(article["id"]),
                "title": article.get("title"),
                "url": article.get("url"),
                "success": False,
                "error": updated.get("parse_error")
                or "Agent reported failure (no detail)",
            }

        error = "Agent did not update article"
        mark_article_parse_failed(db_path, int(article["id"]), error)
        return {
            "id": int(article["id"]),
            "title": article.get("title"),
            "url": article.get("url"),
            "success": False,
            "error": error,
        }
    except Exception as exc:
        mark_article_parse_failed(db_path, int(article["id"]), str(exc))
        return {
            "id": int(article["id"]),
            "title": article.get("title"),
            "url": article.get("url"),
            "success": False,
            "error": str(exc),
        }
    finally:
        clear_article_processing_claim(db_path, int(article["id"]), owner=owner)
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                logger.debug("Failed to delete temp parser file: %s", tmp_path)


async def run_cycle(limit: int = 1, feed_domain: str | None = None) -> dict:
    """Run one autonomous parser cycle by claiming parseable articles."""
    from commands._common import require_db

    db_path = require_db()
    init_database(db_path)

    candidates = get_unparsed_articles(
        db_path, limit=max(limit * 3, limit), feed_domain=feed_domain
    )
    if not candidates:
        return {"parsed": 0, "failed": 0, "claimed": 0, "results": []}

    owner = f"parser:{os.getpid()}"

    # Claim up to `limit` articles — slice BEFORE claiming to avoid
    # leaking claims for articles we won't process
    candidate_ids = [int(a["id"]) for a in candidates][:limit]
    claimed_ids = claim_articles_for_processing(db_path, candidate_ids, "parse", owner)
    claimed_articles = [a for a in candidates if int(a["id"]) in claimed_ids]

    if not claimed_articles:
        return {"parsed": 0, "failed": 0, "claimed": 0, "results": []}

    # Process concurrently with semaphore
    sem = asyncio.Semaphore(5)
    results: list[dict] = []

    async def _parse_one(article: dict) -> dict:
        async with sem:
            result = await _parse_claimed_article(article, owner)
            return result

    results = await asyncio.gather(*(_parse_one(a) for a in claimed_articles))

    parsed = sum(1 for r in results if r.get("success"))
    failed = sum(1 for r in results if not r.get("success"))

    return {
        "parsed": parsed,
        "failed": failed,
        "claimed": len(claimed_articles),
        "results": results,
    }


def get_agent(task_context: dict | None = None) -> FunctionAgent:
    """Create and configure the News Parser Agent.

    Args:
        task_context: Dict with keys for conditional skill loading.
            If None, uses empty context (all core skills loaded).
    """
    api_base = getenv("API_BASE", "")
    api_key = getenv("API_KEY", "")
    model = getenv("MODEL", "")
    if not api_base:
        raise ValueError("Missing API_BASE env.")

    from agents.tools import read_file, run_shell_command, save_lesson

    ctx = task_context or {}

    return FunctionAgent(
        name="NewsParser",
        description=(
            "Parser agent that handles one claimed article at a time and "
            "updates the article record with verified parsed output."
        ),
        tools=[run_shell_command, read_file, save_lesson],
        llm=OpenAILike(
            model=model,
            api_base=api_base,
            api_key=api_key,
            is_chat_model=True,
            is_function_calling_model=True,
        ),
        system_prompt=compose_agent_instructions("parser", ctx),
        streaming=True,
        verbose=False,
    )


async def run(task: str, task_context: dict | None = None):
    """Run the News Parser Agent with a task prompt.

    Parses a single article. The task must contain article information
    (ID, title, HTML file path, URL) so the agent knows what to parse.

    Args:
        task: Task prompt containing article details for parsing.
        task_context: Optional dict for conditional skill loading.

    Returns:
        The final text response from the agent.
    """
    return await run_agent(lambda: get_agent(task_context), task)


async def run_autonomous(task: str = ""):
    """Run the autonomous parser schedule entry."""
    return await run_cycle(limit=20)
