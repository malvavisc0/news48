"""Parse command - parse unparsed articles from the database using LLM."""

import asyncio
import logging
import os
import tempfile

import typer

from agents import run_parser
from database import (
    claim_articles_for_processing,
    clear_article_processing_claim,
    get_article_by_id,
    get_parse_failed_articles,
    get_unparsed_articles,
    mark_article_parse_failed,
    reset_article_parse,
)

from ._common import emit_error, emit_json, require_db, status_msg

logger = logging.getLogger(__name__)


def _get_temp_file_path(content: str) -> str:
    """Create a temp file with content and return its path.

    This is a separate function to ensure the file is not garbage collected
    while the agent is using it.

    Args:
        content: The content to write to the temp file.

    Returns:
        The path to the temp file.
    """
    tmp = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt")
    tmp.write(content)
    tmp.close()
    logger.debug(f"Created temp file: {tmp.name}")
    return tmp.name


async def _parse(article_id: int, *, force: bool = False) -> dict:
    """Parse a single article by ID.

    Claims the article, creates a temp HTML file, runs the parser agent,
    verifies the update, and cleans up. Uses run_agent() from _run.py
    (same pattern as planner/executor).

    Args:
        article_id: The article ID to parse (required).
        force: Override active claims or re-parse already-parsed articles.

    Returns:
        A dict with the parse result for this article.
    """
    require_db()
    claim_owner = f"parse:{os.getpid()}"

    article = get_article_by_id(article_id)
    if not article:
        return {
            "id": article_id,
            "success": False,
            "error": f"Article not found: {article_id}",
        }
    if not article.get("content"):
        return {
            "id": article_id,
            "success": False,
            "error": f"Article {article_id} has no content. " "Download it first.",
        }
    if article.get("parsed_at") and not force:
        return {
            "id": article_id,
            "success": False,
            "error": (
                f"Article {article_id} is already parsed. "
                "Use --force to parse it again."
            ),
        }

    if force or article.get("parse_failed"):
        reset_article_parse(article_id)

    claimed = claim_articles_for_processing(
        [article_id],
        "parse",
        claim_owner,
        force=force,
    )
    if article_id not in claimed:
        return {
            "id": article_id,
            "success": False,
            "error": (
                f"Article {article_id} is already being processed. "
                "Use --force to override the active claim."
            ),
        }

    tmp_path = None
    try:
        tmp_path = _get_temp_file_path(article["content"])

        task = "\n".join(
            [
                "Parse the following article.",
                "Article ID: " + str(article["id"]),
                "Title: " + str(article["title"]),
                "HTML file path: " + tmp_path,
                "URL: " + str(article["url"]),
            ]
        )
        status_msg(f"Parsing: {article['title']}")

        # Delegate to the parser agent for this explicitly claimed article.
        agent_response = await run_parser(task)

        # Verify the agent actually updated the article
        updated_article = get_article_by_id(article["id"])
        if updated_article and updated_article.get("parsed_at"):
            status_msg(f"  Parsed: {updated_article['title']}")
            return {
                "id": article_id,
                "title": updated_article["title"],
                "url": article["url"],
                "success": True,
            }

        # If the agent already reported a specific failure via
        # `articles fail`, preserve that error instead of overwriting.
        if updated_article and updated_article.get("parse_failed"):
            agent_error = (
                updated_article.get("parse_error")
                or "Agent reported failure (no detail)"
            )
            status_msg(f"  Parse failed: {agent_error}")
            return {
                "id": article_id,
                "title": article["title"],
                "url": article["url"],
                "success": False,
                "error": agent_error,
            }

        # Agent truly did nothing — no update, no explicit failure
        error = (agent_response or "").strip() or "Agent did not update article"
        status_msg(f"  Parse failed: {error}")
        mark_article_parse_failed(article["id"], error)
        return {
            "id": article_id,
            "title": article["title"],
            "url": article["url"],
            "success": False,
            "error": error,
        }

    except Exception as e:
        status_msg(f"  Failed to parse {article['url']}: {e}")
        mark_article_parse_failed(article["id"], str(e))
        return {
            "id": article_id,
            "title": article["title"],
            "url": article["url"],
            "success": False,
            "error": str(e),
        }
    finally:
        clear_article_processing_claim(
            article["id"],
            owner=claim_owner,
        )
        if tmp_path:
            try:
                os.unlink(tmp_path)
                logger.debug(f"Deleted temp file: {tmp_path}")
            except Exception:
                pass


def parse(
    limit: int = typer.Option(
        10, "--limit", "-l", help="Maximum number of articles to parse"
    ),
    delay: float = typer.Option(
        1.0, "--delay", "-d", help="Delay between parse operations in seconds"
    ),
    retry: bool = typer.Option(
        False, "--retry", "-r", help="Retry parsing failed articles"
    ),
    feed: str = typer.Option(None, "--feed", help="Filter by feed domain"),
    article: int = typer.Option(
        None, "--article", help="Parse a specific article by ID"
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Override active claims or re-parse a specific article",
    ),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Parse unparsed articles from the database using the LLM agent.

    For each article:
    1. Creates a temporary file with the article HTML content
    2. Runs the news parser agent to extract structured data
    3. Streams tool call events to show progress
    4. The agent updates the article via CLI commands
    5. Verifies the article was updated successfully

    Articles must be fetched first using the 'fetch' command. This command
    processes articles that haven't been parsed yet.

    Use --retry to parse articles that previously failed parsing.
    Use --article to target a specific article by ID.

    Args:
        limit: Maximum number of articles to parse.
        delay: Delay between parse operations in seconds.
        retry: Retry parsing failed articles.
        feed: Optional domain to filter by.
        article: Parse a specific article by ID.
        output_json: Output as JSON instead of human-readable text.
    """
    # Single article mode
    if article is not None:
        try:
            result = asyncio.run(_parse(article, force=force))
        except SystemExit:
            raise
        except Exception as e:
            emit_error(str(e), as_json=output_json)

        if not result.get("success") and result.get("error"):
            emit_error(result["error"], as_json=output_json)

        data = {
            "parsed": 1 if result["success"] else 0,
            "failed": 0 if result["success"] else 1,
            "total": 1,
            "results": [result],
        }

        if output_json:
            emit_json(data)
        else:
            if result["success"]:
                print(f"Parsed article {article}: {result.get('title')}")
            else:
                print(f"Failed to parse article {article}: {result['error']}")
        return

    # Batch mode: find articles and parse each one
    require_db()

    if retry:
        candidates = get_parse_failed_articles(limit, feed_domain=feed)
        if not candidates:
            status_msg("No failed articles found to retry")
            data = {
                "feed_filter": feed,
                "parsed": 0,
                "failed": 0,
                "total": 0,
                "retry": True,
                "results": [],
            }
            if output_json:
                emit_json(data)
            else:
                print("No failed articles found to retry")
            return
        status_msg(f"Found {len(candidates)} failed articles to retry")
    else:
        candidates = get_unparsed_articles(limit, feed_domain=feed)
        if not candidates:
            status_msg("No unparsed articles found")
            data = {
                "feed_filter": feed,
                "parsed": 0,
                "failed": 0,
                "total": 0,
                "retry": False,
                "results": [],
            }
            if output_json:
                emit_json(data)
            else:
                print("No unparsed articles found")
            return
        status_msg(f"Found {len(candidates)} unparsed articles")

    # Use a single event loop with concurrent processing
    async def _parse_batch(
        candidates: list[dict],
        force: bool,
        delay: float,
        feed_filter: str | None,
        is_retry: bool,
    ) -> dict:
        """Parse multiple articles concurrently."""
        sem = asyncio.Semaphore(5)

        async def _parse_one(candidate: dict) -> dict:
            async with sem:
                result = await _parse(candidate["id"], force=force)
                if delay > 0:
                    await asyncio.sleep(delay)
                return result

        results = await asyncio.gather(*(_parse_one(c) for c in candidates))

        parsed = sum(1 for r in results if r.get("success"))
        failed = sum(1 for r in results if not r.get("success"))

        return {
            "feed_filter": feed_filter,
            "parsed": parsed,
            "failed": failed,
            "total": len(candidates),
            "retry": is_retry,
            "results": list(results),
        }

    try:
        data = asyncio.run(
            _parse_batch(
                candidates,
                force=force or retry,
                delay=delay,
                feed_filter=feed,
                is_retry=retry,
            )
        )
    except SystemExit:
        raise
    except Exception as e:
        emit_error(str(e), as_json=output_json)
        return

    if output_json:
        emit_json(data)
    else:
        print(
            f"Parsed {data['parsed']} of {data['total']} "
            f"articles, {data['failed']} failed"
        )
