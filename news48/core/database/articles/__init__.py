"""Article CRUD, search, stats, and query operations using SQLAlchemy ORM.

This package splits the original monolithic articles.py into focused sub-modules
while preserving all public import paths for backward compatibility.
"""

# Re-export all public symbols so that existing imports continue to work:
#   from news48.core.database.articles import get_article_by_id
#   from news48.core.database import get_article_by_id  (via parent __init__)

from ._browsing import (
    get_all_categories,
    get_all_countries,
    get_articles_by_category,
    get_articles_by_tag,
    get_related_articles,
    get_topic_clusters,
    search_articles,
)
from ._claims import (
    claim_articles_for_processing,
    clear_article_processing_claim,
    release_stale_article_claims,
)
from ._constants import _CLAIM_TIMEOUT_MINUTES, _VALID_PROCESSING_ACTIONS
from ._mutations import (
    delete_article,
    increment_view_count,
    insert_articles,
    mark_article_download_failed,
    mark_article_parse_failed,
    patch_article_fields,
    reset_article_download,
    reset_article_parse,
    set_article_breaking,
    set_article_featured,
    update_article,
    update_article_fact_check,
)
from ._queries import (
    get_article_by_id,
    get_article_by_url,
    get_article_detail,
    get_articles_older_than_hours,
    get_articles_paginated,
    get_articles_with_missing_fields,
    get_download_failed_articles,
    get_empty_articles,
    get_expiring_articles,
    get_parse_failed_articles,
    get_unparsed_articles,
)
from ._stats import get_article_stats, get_feed_stats, get_fetch_stats, get_web_stats

__all__ = [
    "claim_articles_for_processing",
    "clear_article_processing_claim",
    "delete_article",
    "get_all_categories",
    "get_all_countries",
    "get_article_by_id",
    "get_article_by_url",
    "get_article_detail",
    "get_article_stats",
    "get_articles_by_category",
    "get_articles_by_tag",
    "get_articles_older_than_hours",
    "get_articles_paginated",
    "get_articles_with_missing_fields",
    "get_download_failed_articles",
    "get_empty_articles",
    "get_expiring_articles",
    "get_feed_stats",
    "get_fetch_stats",
    "get_parse_failed_articles",
    "get_related_articles",
    "get_topic_clusters",
    "get_unparsed_articles",
    "get_web_stats",
    "increment_view_count",
    "insert_articles",
    "mark_article_download_failed",
    "mark_article_parse_failed",
    "patch_article_fields",
    "release_stale_article_claims",
    "reset_article_download",
    "reset_article_parse",
    "search_articles",
    "set_article_breaking",
    "set_article_featured",
    "update_article",
    "update_article_fact_check",
]
