"""News parser agent module.

Provides a factory for the NewsParserAgent, a LlamaIndex FunctionAgent that
extracts structured article data from raw HTML pages.  The agent can detect
and reuse existing bash+python parser scripts or generate new ones on the fly.
"""

import logging
from typing import Optional

from llama_index.core.agent.workflow import FunctionAgent
from llama_index.llms.openai_like import OpenAILike
from pydantic import BaseModel, Field

from agents.instructions import load_agent_instructions

logger = logging.getLogger(__name__)


class NewsParsingResult(BaseModel):
    title: str = Field(description="Original article headline/title")
    new_title: str = Field(
        description=(
            "Improved headline/title that is factual, informative, "
            "and not clickbait or sensationalist"
        )
    )
    content: str = Field(
        description=(
            "Comprehensive text of the article containing all important "
            "information including names, references, key facts, and details"
        )
    )
    published_date: Optional[str] = Field(
        default=None, description="Publication date (ISO 8601 preferred)"
    )
    sentiment: Optional[str] = Field(
        default=None,
        description=(
            "Overall sentiment: 'positive', 'negative', or 'neutral'"
        ),
    )
    categories: list[str] = Field(
        default_factory=list,
        description=(
            "List of categories/topics the article belongs to "
            "(e.g., technology, politics, sports, business, entertainment)"
        ),
    )
    tags: list[str] = Field(
        default_factory=list,
        description=(
            "List of specific keywords/tags extracted from the article"
        ),
    )
    summary: Optional[str] = Field(
        default="",
        description="Brief summary of the article (max 3 sentences)",
    )
    countries: list[str] = Field(
        default_factory=list,
        description=(
            "List of countries mentioned or involved in the article "
            "(e.g., Pakistan, Afghanistan, United States)"
        ),
    )
    image_url: Optional[str] = Field(
        default=None,
        description=(
            "Primary/hero image URL from the article "
            "(prefer large, high-quality images over icons/logos)"
        ),
    )
    language: Optional[str] = Field(
        default=None,
        description=(
            "ISO 639-1 language code of the article content "
            "(e.g., en, de, fr)"
        ),
    )

    success: bool = Field(
        default=True, description="Whether the parsing was successful or not"
    )
    error: str = Field(
        default="",
        description="If there's an error, an explanation of what went wrong",
    )


def get_agent(llm: OpenAILike) -> FunctionAgent:
    """Create and configure the News Parser Agent.

    Args:
        llm: The LLM instance to use for the agent's reasoning.

    Returns:
        A configured FunctionAgent ready for article parsing.
    """
    from agents.tools import read_file, run_shell_command

    return FunctionAgent(
        name="NewsParser",
        description=(
            "Parses HTML article pages, generates and reuses parser scripts "
            "for extracting structured article data (title, content, author, "
            "date, etc.) from news websites."
        ),
        tools=[run_shell_command, read_file],
        llm=llm,
        system_prompt=load_agent_instructions("parser"),
        streaming=True,
        verbose=False,
        output_cls=NewsParsingResult,
    )
