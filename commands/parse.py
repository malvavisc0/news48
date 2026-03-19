"""Parse command - parse unparsed articles from the database using LLM."""

import asyncio
import logging
import tempfile
from datetime import datetime, timezone

import typer
from llama_index.core.agent.workflow import (
    AgentStreamStructuredOutput,
    ToolCall,
)

from agents import get_news_parser_agent
from agents.parser import NewsParsingResult
from config import ParserAgent as ParserAgentConfig
from database import get_unparsed_articles, init_database, update_article
from helpers import get_llm
from helpers.url import get_base_url

from ._common import console, require_db

logger = logging.getLogger(__name__)


async def _parse(limit: int, delay: float) -> None:
    """Parse unparsed articles from the database.

    Args:
        limit: Maximum number of articles to parse.
        delay: Delay between parse operations in seconds.
    """
    db_path = require_db()

    init_database(db_path)
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
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", delete=True, suffix=".txt"
            ) as tmp_file:
                tmp_file.write(article["content"])

                user_msg = (
                    f"\nParse the next article.\n"
                    f"--------------------------------------\n"
                    f"Title: {article['title']}\n"
                    f"Domain: {get_base_url(article['url'])}\n"
                    f"HTML file path: {tmp_file.name}\n"
                    f"--------------------------------------\n"
                )
                console.print(user_msg)

                handler = agent.run(user_msg=user_msg)

                # Stream tool calls and capture structured result
                parsed_result: NewsParsingResult | None = None
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
                            model = event.get_pydantic_model(NewsParsingResult)
                            if model:
                                parsed_result = model
                        except Exception as e:
                            logger.warning(
                                f"Could not parse structured output: {e}"
                            )

                # Update the article with parsed data
                if parsed_result:
                    parsed_at = datetime.now(timezone.utc).isoformat()
                    # Convert lists to comma-separated strings
                    categories_str = (
                        ", ".join(parsed_result.categories)
                        if parsed_result.categories
                        else None
                    )
                    tags_str = (
                        ", ".join(parsed_result.tags)
                        if parsed_result.tags
                        else None
                    )
                    update_article(
                        db_path=db_path,
                        article_id=article["id"],
                        content=parsed_result.content,
                        author=parsed_result.author,
                        published_at=parsed_result.published_date,
                        sentiment=parsed_result.sentiment,
                        categories=categories_str,
                        tags=tags_str,
                        summary=parsed_result.summary,
                        parsed_at=parsed_at,
                    )
                    title = parsed_result.title or "Article"
                    console.print(f"[green]✓ Parsed: {title}[/green]")
                else:
                    console.print(
                        "[yellow]⚠ No structured result received[/yellow]"
                    )

                parsed += 1
                await asyncio.sleep(delay)
        except Exception as e:
            console.print(f"[red]Failed to parse {article['url']}: {e}[/red]")
            failed += 1

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

    Args:
        limit: Maximum number of articles to parse.
        delay: Delay between parse operations in seconds.
    """
    asyncio.run(_parse(limit, delay))
