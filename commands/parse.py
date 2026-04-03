"""Parse command - parse unparsed articles from the database using LLM."""

import asyncio
import logging
import os
import tempfile
from datetime import datetime, timezone

import typer
from llama_index.core.agent.workflow import (
    AgentStreamStructuredOutput,
    ToolCall,
)
from pydantic import BaseModel

from agents import get_news_parser_agent
from agents.parser import NewsParsingResult
from config import ParserAgent as ParserAgentConfig
from database import (
    get_article_by_id,
    get_parse_failed_articles,
    get_unparsed_articles,
    init_database,
    mark_article_parse_failed,
    reset_article_parse,
    update_article,
)
from helpers import get_llm

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


async def _parse(
    limit: int,
    delay: float,
    retry: bool = False,
    feed_domain: str | None = None,
    article_id: int | None = None,
) -> dict:
    """Parse unparsed articles from the database.

    Args:
        limit: Maximum number of articles to parse.
        delay: Delay between parse operations in seconds.
        retry: If True, parse articles that previously failed parsing.
        feed_domain: Optional domain to filter by.
        article_id: Optional specific article ID to parse.

    Returns:
        A dict with parse results.
    """
    db_path = require_db()

    init_database(db_path)

    if article_id is not None:
        article = get_article_by_id(db_path, article_id)
        if not article:
            return {"error": f"Article not found: {article_id}"}
        if not article.get("content"):
            return {
                "error": f"Article {article_id} has no content. "
                "Download it first."
            }
        reset_article_parse(db_path, article_id)
        articles = [article]
        status_msg(f"Parsing article {article_id}")
    elif retry:
        articles = get_parse_failed_articles(
            db_path, limit, feed_domain=feed_domain
        )
        if not articles:
            status_msg("No failed articles found to retry")
            return {
                "feed_filter": feed_domain,
                "parsed": 0,
                "failed": 0,
                "total": 0,
                "retry": True,
                "results": [],
            }
        status_msg(f"Found {len(articles)} failed articles to retry")
    else:
        articles = get_unparsed_articles(
            db_path, limit, feed_domain=feed_domain
        )
        if not articles:
            status_msg("No unparsed articles found")
            return {
                "feed_filter": feed_domain,
                "parsed": 0,
                "failed": 0,
                "total": 0,
                "retry": False,
                "results": [],
            }
        status_msg(f"Found {len(articles)} unparsed articles")

    llm = get_llm(
        model=ParserAgentConfig.model,
        api_base=ParserAgentConfig.api_base,
        api_key=ParserAgentConfig.api_key,
        context_window=ParserAgentConfig.context_window,
    )
    agent = get_news_parser_agent(llm=llm)

    parsed = 0
    failed = 0
    results = []

    for article in articles:
        # Reset flag when retrying so it can be re-tracked
        if retry:
            reset_article_parse(db_path, article["id"])

        tmp_path = None
        try:
            tmp_path = _get_temp_file_path(article["content"])

            user_msg = (
                f"\nParse the next article.\n"
                f"--------------------------------------\n"
                f"Title: {article['title']}\n"
                f"HTML file path: {tmp_path}\n"
                f"URL: {article['url']}\n"
                f"--------------------------------------\n"
            )
            status_msg(f"Parsing: {article['title']}")

            handler = agent.run(user_msg=user_msg)

            # Stream tool calls and capture structured result
            parse_result: NewsParsingResult | BaseModel | None = None
            async for event in handler.stream_events():
                if isinstance(event, ToolCall):
                    reason = (
                        event.tool_kwargs.get("reason")
                        if event.tool_kwargs
                        else None
                    )
                    reason = reason or f"Calling tool: {event.tool_name}"
                    status_msg(f"  -> {reason}")
                elif isinstance(event, AgentStreamStructuredOutput):
                    try:
                        parse_result = event.get_pydantic_model(
                            model=NewsParsingResult
                        )

                    except Exception as e:
                        logger.warning(
                            f"Could not parse structured output: {e}"
                        )

            # Update the article with parsed data
            if parse_result and isinstance(parse_result, NewsParsingResult):
                if not parse_result.success:
                    raise Exception(parse_result.error)

                parsed_at = datetime.now(timezone.utc).isoformat()
                # Convert lists to comma-separated strings
                categories_str = (
                    ", ".join(parse_result.categories)
                    if parse_result.categories
                    else None
                )
                tags_str = (
                    ", ".join(parse_result.tags) if parse_result.tags else None
                )
                countries_str = (
                    ", ".join(parse_result.countries)
                    if parse_result.countries
                    else None
                )
                update_article(
                    db_path=db_path,
                    article_id=article["id"],
                    content=parse_result.content,
                    published_at=parse_result.published_date,
                    sentiment=parse_result.sentiment,
                    categories=categories_str,
                    tags=tags_str,
                    summary=parse_result.summary,
                    parsed_at=parsed_at,
                    countries=countries_str,
                    title=parse_result.new_title,
                )
                status_msg(f"  Parsed: {parse_result.new_title}")
                parsed += 1
                results.append(
                    {
                        "title": parse_result.new_title,
                        "url": article["url"],
                        "success": True,
                    }
                )
                await asyncio.sleep(delay)
            else:
                status_msg("  No structured result received")
                mark_article_parse_failed(
                    db_path, article["id"], "No structured result received"
                )
                results.append(
                    {
                        "title": article["title"],
                        "url": article["url"],
                        "success": False,
                        "error": "No structured result received",
                    }
                )

        except Exception as e:
            status_msg(f"  Failed to parse {article['url']}: {e}")
            mark_article_parse_failed(db_path, article["id"], str(e))
            failed += 1
            results.append(
                {
                    "title": article["title"],
                    "url": article["url"],
                    "success": False,
                    "error": str(e),
                }
            )
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                    logger.debug(f"Deleted temp file: {tmp_path}")
                except Exception:
                    pass

    return {
        "feed_filter": feed_domain,
        "parsed": parsed,
        "failed": failed,
        "total": len(articles),
        "retry": retry,
        "results": results,
    }


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
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Parse unparsed articles from the database using the LLM agent.

    For each article:
    1. Creates a temporary file with the article HTML content
    2. Runs the news parser agent to extract structured data
    3. Streams tool call events to show progress
    4. Captures the structured output (NewsParsingResult)
    5. Updates the article in the database with parsed content
       and parsed_at timestamp

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
    try:
        data = asyncio.run(
            _parse(
                limit,
                delay,
                retry=retry,
                feed_domain=feed,
                article_id=article,
            )
        )
    except SystemExit:
        raise
    except Exception as e:
        emit_error(str(e), as_json=output_json)
    if "error" in data:
        emit_error(data["error"], as_json=output_json)
    if output_json:
        emit_json(data)
    else:
        print(
            f"Parsed {data['parsed']} of {data['total']} "
            f"articles, {data['failed']} failed"
        )
