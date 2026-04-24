"""SQLAlchemy ORM model definitions for all database tables.

All models inherit from Base defined in database.connection.
"""

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .connection import Base


class Feed(Base):
    """Feed model — represents an RSS/Atom feed source."""

    __tablename__ = "feeds"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    title: Mapped[str | None] = mapped_column(String(512))
    description: Mapped[str | None] = mapped_column(Text)
    icon_url: Mapped[str | None] = mapped_column(String(2048))
    favicon_url: Mapped[str | None] = mapped_column(String(2048))
    language: Mapped[str | None] = mapped_column(String(10), default="en")
    category: Mapped[str | None] = mapped_column(String(255))
    last_fetched_at: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[str | None] = mapped_column(String(64))

    # Relationships
    articles: Mapped[list["Article"]] = relationship(
        back_populates="feed", passive_deletes=True
    )

    # Indexes — prefix-length unique index for URL (MySQL utf8mb4 key limit)
    __table_args__ = (Index("uix_feeds_url", "url", unique=True, mysql_length=768),)


class Fetch(Base):
    """Fetch model — tracks each feed-fetching run."""

    __tablename__ = "fetches"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    started_at: Mapped[str] = mapped_column(String(64), nullable=False)
    completed_at: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default="running", nullable=False)
    feeds_fetched: Mapped[int] = mapped_column(default=0)
    articles_found: Mapped[int] = mapped_column(default=0)

    # Relationships
    articles: Mapped[list["Article"]] = relationship(back_populates="fetch")


class Article(Base):
    """Article model — stores news articles with metadata."""

    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    fetch_id: Mapped[int] = mapped_column(ForeignKey("fetches.id"), nullable=False)
    feed_id: Mapped[int] = mapped_column(ForeignKey("feeds.id"), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    title: Mapped[str | None] = mapped_column(String(1024))
    slug: Mapped[str | None] = mapped_column(String(1024))
    summary: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str | None] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(String(512))
    published_at: Mapped[str | None] = mapped_column(String(64))
    parsed_at: Mapped[str | None] = mapped_column(String(64))
    sentiment: Mapped[str | None] = mapped_column(String(20))
    categories: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[str | None] = mapped_column(Text)
    countries: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(String(2048))
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False)
    is_breaking: Mapped[bool] = mapped_column(Boolean, default=False)
    source_name: Mapped[str | None] = mapped_column(String(512))
    language: Mapped[str | None] = mapped_column(String(10), default="en")
    download_failed: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    download_error: Mapped[str | None] = mapped_column(Text)
    parse_failed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    parse_error: Mapped[str | None] = mapped_column(Text)
    fact_check_status: Mapped[str | None] = mapped_column(String(50))
    fact_check_result: Mapped[str | None] = mapped_column(Text)
    fact_checked_at: Mapped[str | None] = mapped_column(String(64))
    processing_status: Mapped[str | None] = mapped_column(String(50))
    processing_owner: Mapped[str | None] = mapped_column(String(255))
    processing_started_at: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[str] = mapped_column(String(64), nullable=False)

    # Relationships
    feed: Mapped["Feed"] = relationship(back_populates="articles")
    fetch: Mapped["Fetch"] = relationship(back_populates="articles")
    claims: Mapped[list["Claim"]] = relationship(
        back_populates="article",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    # Indexes — FULLTEXT index must be added manually in the migration
    __table_args__ = (
        Index("uix_articles_url", "url", unique=True, mysql_length=768),
        Index("idx_articles_feed_id", "feed_id"),
        Index("idx_articles_fetch_id", "fetch_id"),
        Index("idx_articles_download_failed", "download_failed"),
        Index("idx_articles_parse_failed", "parse_failed"),
        Index("idx_articles_published_at", "published_at"),
        Index("idx_articles_created_at", "created_at"),
        Index("idx_articles_sentiment", "sentiment"),
        Index("idx_articles_fact_check_status", "fact_check_status"),
        Index("idx_articles_is_featured", "is_featured"),
        Index("idx_articles_is_breaking", "is_breaking"),
        Index("idx_articles_parsed_at", "parsed_at"),
        Index(
            "idx_articles_processing",
            "processing_status",
            "processing_started_at",
        ),
        Index("idx_articles_48h", "created_at", "published_at"),
    )


class Claim(Base):
    """Claim model — per-claim fact-check results."""

    __tablename__ = "claims"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), nullable=False
    )
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    verdict: Mapped[str] = mapped_column(String(50), nullable=False)
    evidence_summary: Mapped[str | None] = mapped_column(Text)
    sources: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(64), nullable=False)

    # Relationships
    article: Mapped["Article"] = relationship(back_populates="claims")

    # Indexes
    __table_args__ = (
        Index("idx_claims_article_id", "article_id"),
        Index("idx_claims_verdict", "verdict"),
    )
