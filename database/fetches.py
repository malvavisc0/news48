"""Fetch tracking operations."""

from database.connection import _utcnow, get_connection


def create_fetch(db_path) -> int:
    """Create a new fetch and return the fetch ID.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        The ID of the newly created fetch.
    """
    now = _utcnow()
    with get_connection(db_path) as db:
        cursor = db.execute(
            "INSERT INTO fetches (started_at, status) VALUES (?, ?)",
            (now, "running"),
        )
        db.commit()
        assert cursor.lastrowid is not None
        return cursor.lastrowid


def complete_fetch(
    db_path, fetch_id: int, feeds_fetched: int, articles_found: int
) -> None:
    """Mark a fetch as completed.

    Args:
        db_path: Path to the SQLite database file.
        fetch_id: The ID of the fetch to complete.
        feeds_fetched: Number of feeds that were fetched.
        articles_found: Total number of articles found.
    """
    now = _utcnow()
    with get_connection(db_path) as db:
        db.execute(
            """UPDATE fetches
               SET completed_at = ?, status = ?, feeds_fetched = ?,
                   articles_found = ?
               WHERE id = ?""",
            (now, "completed", feeds_fetched, articles_found, fetch_id),
        )
        db.commit()


def fail_fetch(db_path, fetch_id: int) -> None:
    """Mark a fetch as failed.

    Args:
        db_path: Path to the SQLite database file.
        fetch_id: The ID of the fetch to mark as failed.
    """
    now = _utcnow()
    with get_connection(db_path) as db:
        db.execute(
            "UPDATE fetches SET completed_at = ?, status = ? WHERE id = ?",
            (now, "failed", fetch_id),
        )
        db.commit()


def list_fetches(db_path, limit: int = 20) -> list[dict]:
    """List recent fetches ordered by most recent first.

    Args:
        db_path: Path to the SQLite database file.
        limit: Maximum number of fetches to return.

    Returns:
        A list of dicts with fetch data.
    """
    with get_connection(db_path) as db:
        cursor = db.execute(
            "SELECT * FROM fetches ORDER BY started_at DESC LIMIT ?", (limit,)
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
