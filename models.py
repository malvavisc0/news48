from datetime import datetime
from typing import Mapping, Self

from pydantic import BaseModel, Field, field_validator

__all__ = [
    "FeedEntry",
    "FeedResult",
    "Feed",
    "Fetch",
    "Article",
    "FeedSummary",
    "ByparrSolution",
]


class FeedEntry(BaseModel):
    """A single entry from an RSS/Atom feed."""

    url: str = Field(description="URL of the feed entry")
    title: str | None = Field(
        default=None, description="Title of the feed entry"
    )
    summary: str | None = Field(
        default=None, description="Summary/description of the entry"
    )
    author: str | None = Field(default=None, description="Author of the entry")
    published_at: str | None = Field(
        default=None, description="Publication date"
    )
    image_url: str | None = Field(
        default=None,
        description="Primary image URL from feed enclosure/media",
    )


class FeedResult(BaseModel):
    """Result of a feed fetch operation."""

    url: str = Field(description="URL of the feed")
    title: str | None = Field(default=None, description="Title of the feed")
    entry_count: int = Field(
        default=0, ge=0, description="Number of entries in the feed"
    )
    valid_articles_count: int = Field(
        default=0,
        ge=0,
        description="Number of valid articles (from current month)",
    )
    entries: list[FeedEntry] = Field(
        default_factory=list, description="List of feed entries"
    )
    success: bool = Field(
        default=False, description="Whether the fetch was successful"
    )
    error: str | None = Field(
        default=None, description="Error message if fetch failed"
    )

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not v:
            raise ValueError("URL cannot be empty")
        return v


class Feed(BaseModel):
    """A feed stored in the database."""

    model_config = {"str_strip_whitespace": True}

    id: int | None = Field(default=None, description="Database ID of the feed")
    url: str = Field(description="URL of the feed")
    title: str | None = Field(default=None, description="Title of the feed")
    description: str | None = Field(
        default=None, description="Description of the feed"
    )
    icon_url: str | None = Field(
        default=None, description="URL of the feed icon/logo"
    )
    favicon_url: str | None = Field(
        default=None, description="URL of the feed favicon"
    )
    language: str | None = Field(
        default="en", description="ISO 639-1 language code of the feed"
    )
    category: str | None = Field(
        default=None, description="Category/topic of the feed"
    )
    last_fetched_at: datetime | None = Field(
        default=None, description="Last time the feed was fetched"
    )
    created_at: datetime = Field(
        description="When the feed was created in the database"
    )
    updated_at: datetime | None = Field(
        default=None, description="Last time the feed was updated"
    )

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not v:
            raise ValueError("URL cannot be empty")
        return v


class Fetch(BaseModel):
    """A fetch operation stored in the database."""

    model_config = {"str_strip_whitespace": True}

    id: int | None = Field(
        default=None, description="Database ID of the fetch"
    )
    started_at: datetime = Field(description="When the fetch started")
    completed_at: datetime | None = Field(
        default=None, description="When the fetch completed"
    )
    status: str = Field(default="running", description="Status of the fetch")
    feeds_fetched: int = Field(
        default=0, ge=0, description="Number of feeds fetched"
    )
    articles_found: int = Field(
        default=0, ge=0, description="Number of articles found"
    )

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in ["running", "completed", "failed"]:
            raise ValueError(f"invalid status: {v}")
        return v


class Article(BaseModel):
    """An article stored in the database."""

    model_config = {"str_strip_whitespace": True}

    id: int | None = Field(
        default=None, description="Database ID of the article"
    )
    fetch_id: int = Field(
        description="ID of the fetch this article belongs to"
    )
    feed_id: int = Field(description="ID of the feed this article belongs to")
    url: str = Field(description="URL of the article")
    title: str | None = Field(default=None, description="Title of the article")
    summary: str | None = Field(
        default=None, description="Summary of the article"
    )
    content: str | None = Field(
        default=None, description="Full content of the article"
    )
    author: str | None = Field(
        default=None, description="Author of the article"
    )
    published_at: datetime | None = Field(
        default=None, description="Publication date of the article"
    )
    parsed_at: datetime | None = Field(
        default=None, description="When the article was parsed"
    )
    sentiment: str | None = Field(
        default=None,
        description="Sentiment: 'positive', 'negative', or 'neutral'",
    )
    categories: list[str] = Field(
        default_factory=list,
        description="List of categories/topics",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="List of keywords/tags",
    )
    countries: list[str] = Field(
        default_factory=list,
        description="List of countries mentioned in the article",
    )
    image_url: str | None = Field(
        default=None, description="Primary image URL for the article"
    )
    view_count: int = Field(
        default=0,
        ge=0,
        description="Number of times the article has been viewed",
    )
    is_featured: bool = Field(
        default=False, description="Whether the article is editor-featured"
    )
    is_breaking: bool = Field(
        default=False, description="Whether the article is breaking news"
    )
    source_name: str | None = Field(
        default=None, description="Denormalized feed/source name"
    )
    language: str | None = Field(
        default="en", description="ISO 639-1 language code of the article"
    )
    download_failed: bool = Field(
        default=False,
        description="Whether the article content download failed",
    )
    download_error: str | None = Field(
        default=None,
        description="Error message from failed download attempt",
    )
    parse_failed: bool = Field(
        default=False,
        description="Whether the article parsing failed",
    )
    parse_error: str | None = Field(
        default=None,
        description="Error message from failed parse attempt",
    )
    created_at: datetime = Field(
        description="When the article was created in the database"
    )

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not v:
            raise ValueError("URL cannot be empty")
        return v


class FeedSummary(BaseModel):
    """Summary of all feed fetch results."""

    successful: list[FeedResult] = Field(
        default_factory=list, description="List of successful feed results"
    )
    failed: list[FeedResult] = Field(
        default_factory=list, description="List of failed feed results"
    )

    @property
    def total(self) -> int:
        """Total number of feeds processed."""
        return len(self.successful) + len(self.failed)

    @property
    def success_rate(self) -> float:
        """Percentage of successful feed fetches."""
        if self.total == 0:
            return 0.0
        return (len(self.successful) / self.total) * 100

    def add_result(self, result: FeedResult) -> Self:
        """Add a feed result to the summary.

        Args:
            result: The FeedResult to add.

        Returns:
            Self for method chaining.
        """
        if result.success:
            self.successful.append(result)
        else:
            self.failed.append(result)
        return self


class ByparrSolution(BaseModel):
    """Solution for bypassing anti-bot protection."""

    cookies: list[tuple[str, str]] = Field(
        default_factory=list, description="Cookies to include in requests"
    )
    headers: Mapping[str, str] = Field(
        default_factory=dict, description="Headers to include in requests"
    )
