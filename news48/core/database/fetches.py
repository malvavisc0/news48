"""Fetch tracking operations using SQLAlchemy ORM."""

from .connection import SessionLocal, _utcnow
from .models import Fetch


def create_fetch() -> int:
    """Create a new fetch and return the fetch ID.

    Returns:
        The ID of the newly created fetch.
    """
    now = _utcnow()
    with SessionLocal() as session:
        fetch = Fetch(started_at=now, status="running")
        session.add(fetch)
        session.flush()
        fetch_id = fetch.id
        session.commit()
        return fetch_id


def complete_fetch(fetch_id: int, feeds_fetched: int, articles_found: int) -> None:
    """Mark a fetch as completed.

    Args:
        fetch_id: The ID of the fetch to complete.
        feeds_fetched: Number of feeds that were fetched.
        articles_found: Total number of articles found.
    """
    now = _utcnow()
    with SessionLocal() as session:
        fetch = session.get(Fetch, fetch_id)
        if fetch:
            fetch.completed_at = now
            fetch.status = "completed"
            fetch.feeds_fetched = feeds_fetched
            fetch.articles_found = articles_found
            session.commit()


def fail_fetch(fetch_id: int) -> None:
    """Mark a fetch as failed.

    Args:
        fetch_id: The ID of the fetch to mark as failed.
    """
    now = _utcnow()
    with SessionLocal() as session:
        fetch = session.get(Fetch, fetch_id)
        if fetch:
            fetch.completed_at = now
            fetch.status = "failed"
            session.commit()


def list_fetches(limit: int = 20) -> list[dict]:
    """List recent fetches ordered by most recent first.

    Args:
        limit: Maximum number of fetches to return.

    Returns:
        A list of dicts with fetch data.
    """
    with SessionLocal() as session:
        fetches = (
            session.query(Fetch).order_by(Fetch.started_at.desc()).limit(limit).all()
        )
        return [fetch.to_dict() for fetch in fetches]
