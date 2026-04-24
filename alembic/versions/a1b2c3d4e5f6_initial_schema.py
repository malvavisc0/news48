"""initial schema

Revision ID: a1b2c3d4e5f6
Revises:
Create Date: 2026-04-22 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create feeds table
    op.create_table(
        "feeds",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("icon_url", sa.String(length=2048), nullable=True),
        sa.Column("favicon_url", sa.String(length=2048), nullable=True),
        sa.Column("language", sa.String(length=10), nullable=True),
        sa.Column("category", sa.String(length=255), nullable=True),
        sa.Column("last_fetched_at", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.String(length=64), nullable=False),
        sa.Column("updated_at", sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    # Prefix-length unique index for URL (MySQL utf8mb4 key limit: 3072 bytes)
    op.execute("CREATE UNIQUE INDEX uix_feeds_url ON feeds (url(768))")

    # Create fetches table
    op.create_table(
        "fetches",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("started_at", sa.String(length=64), nullable=False),
        sa.Column("completed_at", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("feeds_fetched", sa.Integer(), nullable=True),
        sa.Column("articles_found", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create articles table
    op.create_table(
        "articles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("fetch_id", sa.Integer(), nullable=False),
        sa.Column("feed_id", sa.Integer(), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("title", sa.String(length=1024), nullable=True),
        sa.Column("slug", sa.String(length=1024), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("author", sa.String(length=512), nullable=True),
        sa.Column("published_at", sa.String(length=64), nullable=True),
        sa.Column("parsed_at", sa.String(length=64), nullable=True),
        sa.Column("sentiment", sa.String(length=20), nullable=True),
        sa.Column("categories", sa.Text(), nullable=True),
        sa.Column("tags", sa.Text(), nullable=True),
        sa.Column("countries", sa.Text(), nullable=True),
        sa.Column("image_url", sa.String(length=2048), nullable=True),
        sa.Column("view_count", sa.Integer(), nullable=True),
        sa.Column("is_featured", sa.Boolean(), nullable=True),
        sa.Column("is_breaking", sa.Boolean(), nullable=True),
        sa.Column("source_name", sa.String(length=512), nullable=True),
        sa.Column("language", sa.String(length=10), nullable=True),
        sa.Column("download_failed", sa.Boolean(), nullable=False),
        sa.Column("download_error", sa.Text(), nullable=True),
        sa.Column("parse_failed", sa.Boolean(), nullable=False),
        sa.Column("parse_error", sa.Text(), nullable=True),
        sa.Column("fact_check_status", sa.String(length=50), nullable=True),
        sa.Column("fact_check_result", sa.Text(), nullable=True),
        sa.Column("fact_checked_at", sa.String(length=64), nullable=True),
        sa.Column("processing_status", sa.String(length=50), nullable=True),
        sa.Column("processing_owner", sa.String(length=255), nullable=True),
        sa.Column("processing_started_at", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["feed_id"],
            ["feeds.id"],
        ),
        sa.ForeignKeyConstraint(
            ["fetch_id"],
            ["fetches.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Prefix-length unique index for URL (MySQL utf8mb4 key limit: 3072 bytes)
    op.execute("CREATE UNIQUE INDEX uix_articles_url ON articles (url(768))")

    # Create article indexes
    op.create_index("idx_articles_feed_id", "articles", ["feed_id"])
    op.create_index("idx_articles_fetch_id", "articles", ["fetch_id"])
    op.create_index("idx_articles_download_failed", "articles", ["download_failed"])
    op.create_index("idx_articles_parse_failed", "articles", ["parse_failed"])
    op.create_index("idx_articles_published_at", "articles", ["published_at"])
    op.create_index("idx_articles_created_at", "articles", ["created_at"])
    op.create_index("idx_articles_sentiment", "articles", ["sentiment"])
    op.create_index("idx_articles_fact_check_status", "articles", ["fact_check_status"])
    op.create_index("idx_articles_is_featured", "articles", ["is_featured"])
    op.create_index("idx_articles_is_breaking", "articles", ["is_breaking"])
    op.create_index("idx_articles_parsed_at", "articles", ["parsed_at"])
    op.create_index(
        "idx_articles_processing",
        "articles",
        ["processing_status", "processing_started_at"],
    )
    op.create_index("idx_articles_48h", "articles", ["created_at", "published_at"])

    # Create claims table
    op.create_table(
        "claims",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("article_id", sa.Integer(), nullable=False),
        sa.Column("claim_text", sa.Text(), nullable=False),
        sa.Column("verdict", sa.String(length=50), nullable=False),
        sa.Column("evidence_summary", sa.Text(), nullable=True),
        sa.Column("sources", sa.Text(), nullable=True),
        sa.Column("created_at", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["article_id"], ["articles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create claim indexes
    op.create_index("idx_claims_article_id", "claims", ["article_id"])
    op.create_index("idx_claims_verdict", "claims", ["verdict"])

    # Add FULLTEXT index for article search (MySQL-specific)
    op.execute(
        "ALTER TABLE articles ADD FULLTEXT INDEX ft_articles_search "
        "(title, summary, content, tags, categories)"
    )


def downgrade() -> None:
    # Drop FULLTEXT index first
    op.execute("ALTER TABLE articles DROP INDEX ft_articles_search")

    # Drop claim indexes
    op.drop_index("idx_claims_verdict", table_name="claims")
    op.drop_index("idx_claims_article_id", table_name="claims")

    # Drop claims table
    op.drop_table("claims")

    # Drop article prefix-length unique indexes
    op.drop_index("uix_articles_url", table_name="articles")

    # Drop article indexes
    op.drop_index("idx_articles_48h", table_name="articles")
    op.drop_index("idx_articles_processing", table_name="articles")
    op.drop_index("idx_articles_parsed_at", table_name="articles")
    op.drop_index("idx_articles_is_breaking", table_name="articles")
    op.drop_index("idx_articles_is_featured", table_name="articles")
    op.drop_index("idx_articles_fact_check_status", table_name="articles")
    op.drop_index("idx_articles_sentiment", table_name="articles")
    op.drop_index("idx_articles_created_at", table_name="articles")
    op.drop_index("idx_articles_published_at", table_name="articles")
    op.drop_index("idx_articles_parse_failed", table_name="articles")
    op.drop_index("idx_articles_download_failed", table_name="articles")
    op.drop_index("idx_articles_fetch_id", table_name="articles")
    op.drop_index("idx_articles_feed_id", table_name="articles")

    # Drop articles table
    op.drop_table("articles")

    # Drop fetches table
    op.drop_table("fetches")

    # Drop feed prefix-length unique indexes
    op.drop_index("uix_feeds_url", table_name="feeds")

    # Drop feeds table
    op.drop_table("feeds")
