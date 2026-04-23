from typing import Mapping, Self

from pydantic import BaseModel, Field, field_validator

__all__ = [
    "FeedEntry",
    "FeedResult",
    "FeedSummary",
    "ByparrSolution",
]


class FeedEntry(BaseModel):
    """A single entry from an RSS/Atom feed."""

    url: str = Field(description="URL of the feed entry")
    title: str | None = Field(default=None, description="Title of the feed entry")
    summary: str | None = Field(
        default=None, description="Summary/description of the entry"
    )
    author: str | None = Field(default=None, description="Author of the entry")
    published_at: str | None = Field(default=None, description="Publication date")
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
    success: bool = Field(default=False, description="Whether the fetch was successful")
    error: str | None = Field(default=None, description="Error message if fetch failed")

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
