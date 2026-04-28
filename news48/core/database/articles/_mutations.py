"""Article mutation operations: insert, update, delete, and flag management."""

import logging
import re

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from news48.core.helpers.text import strip_html_tags as _strip_html_tags
from news48.core.helpers.text import strip_markdown as _strip_markdown

from ..connection import SessionLocal, _utcnow
from ..models import Article

logger = logging.getLogger(__name__)

# Matches currency ($400,000, €5B), percentages (38%), and plain
# numbers with optional magnitude suffixes (12K, 1.5M, etc.).
_NUMBER_RE = re.compile(
    r"[\$€£]?\d[\d,.]*\s*[KkMmBbTt]?(?:\s*(?:million|billion|trillion))?"
    r"|\d+%"
)


def _extract_numbers(text: str) -> set[str]:
    """Extract normalized number tokens from text for comparison."""
    return {m.group().strip().lower() for m in _NUMBER_RE.finditer(text)}


def _numbers_ok(original: str, rewritten: str) -> bool:
    """Check whether currency amounts from *original* survive in *rewritten*.

    The most common LLM failure is dropping the currency symbol and
    leading digits from monetary amounts (e.g. "$400,000" → "00K").
    This function checks that every currency-prefixed number in the
    original has a corresponding currency-prefixed number in the
    rewrite.  Abbreviations are fine as long as the currency symbol
    and leading digit are preserved.
    """
    try:
        # Find currency amounts in original: $400,000, €8B, £3.2M, etc.
        _CURRENCY_RE = re.compile(
            r"[\$€£]\s*\d[\d,.]*\s*[KkMmBbTt]?(?:\s*(?:million|billion|trillion))?"
        )
        orig_currencies = _CURRENCY_RE.findall(original)
        if not orig_currencies:
            return True
        new_currencies = _CURRENCY_RE.findall(rewritten)
        # If the original had more currency amounts than the
        # rewrite, the LLM dropped some.
        if len(new_currencies) < len(orig_currencies):
            return False
        return True
    except Exception:
        return True  # On error, don't block the update.


def insert_articles(
    fetch_id: int,
    feed_id: int,
    entries: list[dict],
    source_name: str | None = None,
) -> int:
    """Batch insert articles from feed entries, ignoring duplicates by URL.

    Args:
        fetch_id: The current fetch ID.
        feed_id: The feed ID these articles belong to.
        entries: List of dicts with keys: url, title, summary, author,
            published_at, image_url.
        source_name: Optional denormalized feed/source name.

    Returns:
        Number of new articles inserted.
    """
    now = _utcnow()
    count = 0
    _log = logging.getLogger(__name__)
    skipped_no_url = 0
    duplicates = 0

    with SessionLocal() as session:
        for entry in entries:
            if not entry.get("url"):
                skipped_no_url += 1
                continue
            try:
                with session.begin_nested():
                    article = Article(
                        fetch_id=fetch_id,
                        feed_id=feed_id,
                        url=entry["url"],
                        title=_strip_html_tags(entry.get("title")),
                        summary=_strip_html_tags(entry.get("summary")),
                        author=entry.get("author"),
                        published_at=entry.get("published_at"),
                        created_at=now,
                        source_name=source_name or entry.get("source_name"),
                        image_url=entry.get("image_url"),
                    )
                    session.add(article)
                    session.flush()
                count += 1
            except IntegrityError:
                duplicates += 1

        if entries:
            _log.info(
                "insert_articles: %d entries, %d new, "
                "%d duplicates, %d no-url",
                len(entries),
                count,
                duplicates,
                skipped_no_url,
            )
        session.commit()

    return count


def update_article(
    article_id: int,
    content: str,
    author: str | None = None,
    published_at: str | None = None,
    sentiment: str | None = None,
    categories: str | None = None,
    tags: str | None = None,
    summary: str | None = None,
    parsed_at: str | None = None,
    countries: str | None = None,
    title: str | None = None,
    image_url: str | None = None,
    language: str | None = None,
) -> None:
    """Update an article with parsed content from the parser agent.

    Metadata fields (author, published_at, image_url) are only
    updated if the current value is NULL/empty, preserving accurate
    feed-provided values over LLM extractions.
    """
    summary = _strip_markdown(_strip_html_tags(summary)) or None
    title = _strip_markdown(_strip_html_tags(title)) or None
    content = _strip_markdown(_strip_html_tags(content)) or ""

    if sentiment:
        sentiment = sentiment.lower()
    if categories:
        categories = categories.lower()
    if tags:
        tags = tags.lower()
    if countries:
        countries = countries.lower()

    with SessionLocal() as session:
        article = session.get(Article, article_id)
        if article:
            # Guard against LLM number-drop: if the rewrite lost
            # significant digit sequences (e.g. "$400,000" → "00K"),
            # fall back to the original text for that field.
            if (
                title
                and article.title
                and not _numbers_ok(article.title, title)
            ):
                logger.error(
                    "Article %d: title rewrite dropped numbers — "
                    "keeping original. original=%r rewritten=%r",
                    article_id,
                    article.title[:120],
                    title[:120],
                )
                title = article.title
            if (
                content
                and article.content
                and not _numbers_ok(article.content, content)
            ):
                logger.error(
                    "Article %d: content rewrite dropped numbers — "
                    "keeping original.",
                    article_id,
                )
                content = article.content

            article.content = content
            # Only update metadata if current value is NULL/empty
            if author and not article.author:
                article.author = author
            if published_at and not article.published_at:
                article.published_at = published_at
            if sentiment:
                article.sentiment = sentiment
            if categories:
                article.categories = categories
            if tags:
                article.tags = tags
            if summary and not article.summary:
                article.summary = summary
            if parsed_at:
                article.parsed_at = parsed_at
            if countries:
                article.countries = countries
            if title:
                from news48.core.helpers.url import slugify

                article.title = title
                article.slug = f"{slugify(title)}-{article_id}"
            if image_url and not article.image_url:
                article.image_url = image_url
            if language:
                article.language = language
            session.commit()


def update_article_fact_check(
    article_id: int,
    status: str,
    result: str | None = None,
    force: bool = False,
) -> bool:
    """Update the fact-check fields of an article."""
    valid_statuses = {
        "verified",
        "disputed",
        "unverifiable",
        "mixed",
        "fact_check_error",
    }
    if status.lower() not in valid_statuses:
        raise ValueError(
            f"Invalid fact_check_status '{status}'. "
            f"Valid: {', '.join(sorted(valid_statuses))}"
        )
    now = _utcnow()
    with SessionLocal() as session:
        article = session.get(Article, article_id)
        if article and (force or article.fact_check_status is None):
            article.fact_check_status = status.lower()
            article.fact_check_result = result
            article.fact_checked_at = now
            session.commit()
            return True
        return False


def patch_article_fields(
    article_id: int,
    summary: str | None = None,
    categories: str | None = None,
    sentiment: str | None = None,
    tags: str | None = None,
) -> None:
    """Patch specific metadata fields on an article without touching content.

    Only updates fields that are provided (non-None).
    Does NOT modify content, title, parsed_at, or other fields.
    """
    with SessionLocal() as session:
        article = session.get(Article, article_id)
        if not article:
            return
        if summary:
            article.summary = _strip_markdown(_strip_html_tags(summary))
        if categories:
            article.categories = categories.lower()
        if sentiment:
            article.sentiment = sentiment.lower()
        if tags:
            article.tags = tags.lower()
        session.commit()


def mark_article_download_failed(article_id: int, error: str) -> None:
    """Mark an article as having a failed download."""
    with SessionLocal() as session:
        article = session.get(Article, article_id)
        if article:
            article.download_failed = True
            article.download_error = error
            session.commit()


def mark_article_parse_failed(article_id: int, error: str) -> None:
    """Mark an article as having a failed parse."""
    with SessionLocal() as session:
        article = session.get(Article, article_id)
        if article and article.parse_failed is False:
            article.parse_failed = True
            article.parse_error = error
            session.commit()


def reset_article_download(article_id: int) -> None:
    """Reset download_failed flag and clear download_error for an article."""
    with SessionLocal() as session:
        article = session.get(Article, article_id)
        if article:
            article.download_failed = False
            article.download_error = None
            session.commit()


def reset_article_parse(article_id: int) -> None:
    """Reset parse_failed flag and clear parse_error for an article."""
    with SessionLocal() as session:
        article = session.get(Article, article_id)
        if article:
            article.parse_failed = False
            article.parse_error = None
            article.parsed_at = None
            session.commit()


def delete_article(article_id: int) -> bool:
    """Delete an article by ID."""
    with SessionLocal() as session:
        article = session.get(Article, article_id)
        if article:
            session.delete(article)
            session.commit()
            return True
        return False


def set_article_featured(article_id: int, featured: bool = True) -> None:
    """Mark/unmark an article as featured."""
    with SessionLocal() as session:
        article = session.get(Article, article_id)
        if article:
            article.is_featured = featured
            session.commit()


def set_article_breaking(article_id: int, breaking: bool = True) -> None:
    """Mark/unmark an article as breaking news."""
    with SessionLocal() as session:
        article = session.get(Article, article_id)
        if article:
            article.is_breaking = breaking
            session.commit()


def increment_view_count(article_id: int) -> None:
    """Atomically increment the view count for an article."""
    with SessionLocal() as session:
        session.execute(
            text(
                "UPDATE articles SET view_count = view_count + 1"
                " WHERE id = :id"
            ),
            {"id": article_id},
        )
        session.commit()
