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
    get_parse_failed_articles,
    get_unparsed_articles,
    init_database,
    mark_article_parse_failed,
    reset_article_parse,
    update_article,
)
from helpers import get_llm

from ._common import console, require_db

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


async def _parse(limit: int, delay: float, retry: bool = False) -> None:
    """Parse unparsed articles from the database.

    Args:
        limit: Maximum number of articles to parse.
        delay: Delay between parse operations in seconds.
        retry: If True, parse articles that previously failed parsing.
    """
    db_path = require_db()

    init_database(db_path)
    if retry:
        articles = get_parse_failed_articles(db_path, limit)
        if not articles:
            console.print("[yellow]No failed articles found to retry[/yellow]")
            return
        console.print(f"Found {len(articles)} failed articles to retry")
    else:
        articles = get_unparsed_articles(db_path, limit)
        if not articles:
            console.print("[yellow]No unparsed articles found[/yellow]")
            return
        console.print(f"Found {len(articles)} unparsed articles")

    llm = get_llm(
        model=ParserAgentConfig.model,
        api_base=ParserAgentConfig.api_base,
        api_key=ParserAgentConfig.api_key,
        context_window=ParserAgentConfig.context_window,
    )
    agent = get_news_parser_agent(llm=llm)

    parsed = 0
    failed = 0
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
            console.print(user_msg)

            handler = agent.run(user_msg=user_msg)

            # Stream tool calls and capture structured result
            results: NewsParsingResult | BaseModel | None = None
            async for event in handler.stream_events():
                if isinstance(event, ToolCall):
                    intent = (
                        event.tool_kwargs.get("intent")
                        if event.tool_kwargs
                        else None
                    )
                    intent = intent or f"Calling tool: {event.tool_name}"
                    console.print(f"[cyan]→[/cyan] {intent}")
                elif isinstance(event, AgentStreamStructuredOutput):
                    try:
                        results = event.get_pydantic_model(
                            model=NewsParsingResult
                        )

                    except Exception as e:
                        logger.warning(
                            f"Could not parse structured output: {e}"
                        )

            # Update the article with parsed data
            if results and isinstance(results, NewsParsingResult):
                if not results.success:
                    raise Exception(results.error)

                parsed_at = datetime.now(timezone.utc).isoformat()
                # Convert lists to comma-separated strings
                categories_str = (
                    ", ".join(results.categories)
                    if results.categories
                    else None
                )
                tags_str = ", ".join(results.tags) if results.tags else None
                countries_str = (
                    ", ".join(results.countries) if results.countries else None
                )
                update_article(
                    db_path=db_path,
                    article_id=article["id"],
                    content=results.content,
                    published_at=results.published_date,
                    sentiment=results.sentiment,
                    categories=categories_str,
                    tags=tags_str,
                    summary=results.summary,
                    parsed_at=parsed_at,
                    countries=countries_str,
                    title=results.new_title,
                )
                console.print(f"[green]✓ Parsed: {results.new_title}[/green]")
                parsed += 1
                await asyncio.sleep(delay)
            else:
                console.print(
                    "[yellow]⚠ No structured result received[/yellow]"
                )
                mark_article_parse_failed(
                    db_path, article["id"], "No structured result received"
                )

        except Exception as e:
            console.print(f"[red]Failed to parse {article['url']}: {e}[/red]")
            mark_article_parse_failed(db_path, article["id"], str(e))
            failed += 1
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                    logger.debug(f"Deleted temp file: {tmp_path}")
                except Exception:
                    pass

    console.print(
        f"[green]Parsed: {parsed}[/green] | [red]Failed: {failed}[/red]"
    )


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

    Args:
        limit: Maximum number of articles to parse.
        delay: Delay between parse operations in seconds.
        retry: Retry parsing failed articles.
    """
    asyncio.run(_parse(limit, delay, retry))
