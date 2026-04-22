"""Feed CRUD operations using SQLAlchemy ORM."""

from sqlalchemy.exc import IntegrityError

from database.connection import SessionLocal, _utcnow
from database.models import Feed


def seed_feeds(urls: list[str]) -> int:
    """Insert feeds from seed file, ignoring duplicates.

    Args:
        urls: List of feed URLs to insert.

    Returns:
        Number of new feeds inserted.
    """
    now = _utcnow()
    count = 0
    with SessionLocal() as session:
        for url in urls:
            try:
                feed = Feed(url=url, created_at=now)
                session.add(feed)
                session.flush()
                count += 1
            except IntegrityError:
                session.rollback()
        session.commit()
    return count


def get_all_feeds(feed_domain: str | None = None) -> list[dict]:
    """Get all feeds from the database, optionally filtered by domain.

    Args:
        feed_domain: Optional domain to filter feeds by (matched against
            the feed URL using LIKE).

    Returns:
        A list of dicts with feed data (including 'url' and 'id').
    """
    with SessionLocal() as session:
        query = session.query(Feed)
        if feed_domain:
            query = query.filter(Feed.url.like(f"%{feed_domain}%"))
        feeds = query.all()
        return [feed.to_dict() for feed in feeds]


def get_feed_by_url(url: str) -> dict | None:
    """Look up a feed by its URL.

    Args:
        url: The feed URL to look up.

    Returns:
        A dict with feed data, or None if not found.
    """
    with SessionLocal() as session:
        feed = session.query(Feed).filter(Feed.url == url).first()
        return feed.to_dict() if feed else None


def update_feed_metadata(
    feed_id: int,
    title: str,
    description: str | None = None,
    icon_url: str | None = None,
    favicon_url: str | None = None,
) -> None:
    """Update feed metadata after a successful fetch.

    Args:
        feed_id: The ID of the feed to update.
        title: The feed title.
        description: Optional feed description.
        icon_url: Optional URL of the feed icon/logo.
        favicon_url: Optional URL of the feed favicon.
    """
    now = _utcnow()
    with SessionLocal() as session:
        feed = session.get(Feed, feed_id)
        if feed:
            feed.title = title
            feed.description = description
            feed.last_fetched_at = now
            feed.updated_at = now
            if icon_url:
                feed.icon_url = icon_url
            if favicon_url:
                feed.favicon_url = favicon_url
            session.commit()


def get_feed_by_id(feed_id: int) -> dict | None:
    """Look up a feed by its ID.

    Args:
        feed_id: The feed ID to look up.

    Returns:
        A dict with feed data, or None if not found.
    """
    with SessionLocal() as session:
        feed = session.get(Feed, feed_id)
        return feed.to_dict() if feed else None


def get_feed_article_count(feed_id: int) -> int:
    """Get the number of articles for a specific feed.

    Args:
        feed_id: The feed ID to count articles for.

    Returns:
        Number of articles associated with the feed.
    """
    from database.models import Article

    with SessionLocal() as session:
        count = session.query(Article).filter(Article.feed_id == feed_id).count()
        return count


def delete_feed(feed_id: int) -> bool:
    """Delete a feed and its associated articles by feed ID.

    Args:
        feed_id: The ID of the feed to delete.

    Returns:
        True if the feed was deleted, False if not found.
    """
    with SessionLocal() as session:
        feed = session.get(Feed, feed_id)
        if feed:
            session.delete(feed)
            session.commit()
            return True
        return False


def get_feeds_paginated(limit: int = 20, offset: int = 0) -> list[dict]:
    """Get feeds with server-side pagination.

    Args:
        limit: Maximum number of feeds to return.
        offset: Number of feeds to skip.

    Returns:
        A list of dicts with feed data.
    """
    with SessionLocal() as session:
        feeds = session.query(Feed).order_by(Feed.id).limit(limit).offset(offset).all()
        return [feed.to_dict() for feed in feeds]


def get_feed_count() -> int:
    """Get total number of feeds in the database.

    Returns:
        Total number of feeds.
    """
    with SessionLocal() as session:
        return session.query(Feed).count()
