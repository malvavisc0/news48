"""Fact-check agent for autonomous article verification."""

import logging
from os import getenv

from llama_index.core.agent.workflow import FunctionAgent
from llama_index.llms.openai_like import OpenAILike

from agents._run import run_agent
from agents.skills import compose_agent_instructions
from database import get_article_by_id, get_articles_paginated

logger = logging.getLogger(__name__)


async def run_cycle(limit: int = 10) -> dict:
    """Run one fact-check cycle."""
    # Get fact-unchecked articles
    articles, total = get_articles_paginated(limit=limit, status="fact-unchecked")
    if not articles:
        return {"checked": 0, "results": []}

    results = []
    for article in articles:
        try:
            task = (
                f"Fact-check article {article['id']}: {article['title']}\n"
                f"URL: {article['url']}"
            )
            await run_agent(lambda: get_agent({}), task)

            # Check if fact_check_status was updated
            updated = get_article_by_id(article["id"])
            if updated and updated.get("fact_check_status"):
                results.append({"id": article["id"], "success": True})
            else:
                results.append(
                    {
                        "id": article["id"],
                        "success": False,
                        "error": "No verdict",
                    }
                )
        except Exception as exc:
            results.append({"id": article["id"], "success": False, "error": str(exc)})

    checked = sum(1 for r in results if r.get("success"))
    return {"checked": checked, "results": results}


def get_agent(task_context: dict | None = None) -> FunctionAgent:
    """Create and return the Fact-Check Agent."""
    api_base = getenv("API_BASE", "")
    api_key = getenv("API_KEY", "")
    model = getenv("MODEL", "")
    if not api_base:
        raise ValueError("Missing API_BASE env.")

    from agents.tools import (
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
