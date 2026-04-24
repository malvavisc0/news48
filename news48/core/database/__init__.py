"""Database package — re-exports public functions used across the project."""

from .articles import (
    claim_articles_for_processing,
    clear_article_processing_claim,
    delete_article,
    get_article_by_id,
    get_article_by_url,
    get_article_detail,
    get_article_stats,
    get_articles_older_than_hours,
    get_articles_paginated,
    get_articles_with_missing_fields,
    get_download_failed_articles,
    get_empty_articles,
    get_expiring_articles,
    get_feed_stats,
    get_fetch_stats,
    get_parse_failed_articles,
    get_related_articles,
    get_topic_clusters,
    get_unparsed_articles,
    get_web_stats,
    increment_view_count,
    insert_articles,
    mark_article_download_failed,
    mark_article_parse_failed,
    reset_article_download,
    reset_article_parse,
    search_articles,
    set_article_breaking,
    set_article_featured,
    update_article,
    update_article_fact_check,
)
from .claims import (
    compute_overall_verdict,
    delete_claims_for_article,
    get_claims_for_article,
    insert_claims,
)
from .feeds import (
    delete_feed,
    get_all_feeds,
    get_feed_article_count,
    get_feed_by_id,
    get_feed_by_url,
    get_feed_count,
    get_feeds_paginated,
    seed_feeds,
    update_feed_metadata,
)
from .fetches import complete_fetch, create_fetch, fail_fetch, list_fetches
from .retention import (
    check_database_health,
    get_retention_policy_stats,
    purge_articles_older_than_hours,
)
