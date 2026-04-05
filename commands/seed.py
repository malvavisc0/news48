"""Seed command - seed the database with feed URLs from a file."""

import typer

from database import init_database, seed_feeds
from helpers import load_urls

from ._common import emit_error, emit_json, require_db, status_msg


def _seed(seed_file: str) -> dict:
    """Seed the database with feed URLs from a file.

    Args:
        seed_file: Path to the seed file containing feed URLs.

    Returns:
        A dict with seeding results.
    """
    db_path = require_db()

    init_database(db_path)
    urls = load_urls(seed_file)

    status_msg(f"Seeding {len(urls)} feed URLs...")
    count = seed_feeds(db_path, urls)

    return {
        "seeded": count,
        "total_urls": len(urls),
        "skipped": len(urls) - count,
    }


def seed(
    seed_file: str = typer.Argument(
        ..., help="Path to the seed file containing feed URLs"
    ),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Seed the database with feed URLs from a file.

    Args:
        seed_file: Path to the seed file containing feed URLs.
        output_json: Output as JSON instead of human-readable text.
    """
    try:
        data = _seed(seed_file)
    except SystemExit:
        raise
    except Exception as e:
        emit_error(str(e), as_json=output_json)
    if output_json:
        emit_json(data)
    else:
        print(
            f"Seeded {data['seeded']} new feeds "
            f"({data['skipped']} skipped, {data['total_urls']} total)"
        )
