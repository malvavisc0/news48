"""Stats command - show article statistics."""

from database import get_connection, init_database

from ._common import console, require_db


def stats() -> None:
    """Show article statistics.

    Displays:
    - Number of unparsed articles (parsed_at IS NULL)
    - Number of articles with no content (content IS NULL OR content = '')
    """
    db_path = require_db()

    init_database(db_path)

    with get_connection(db_path) as db:
        # Count unparsed articles (parsed_at IS NULL)
        query = "SELECT COUNT(*) FROM articles WHERE parsed_at IS NULL"
        cursor = db.execute(query)
        unparsed_count = cursor.fetchone()[0]

        # Count articles with no content (content IS NULL OR content = '')
        query = "SELECT COUNT(*) FROM articles WHERE content IS NULL OR content = ''"
        cursor = db.execute(query)
        no_content_count = cursor.fetchone()[0]

    console.print("[bold]Article Statistics[/bold]")
    console.print(f"Unparsed articles: {unparsed_count}")
    console.print(f"Articles with no content: {no_content_count}")
