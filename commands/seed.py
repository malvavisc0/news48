"""Seed command - seed the database with feed URLs from a file."""

import json
from datetime import datetime, timezone
from pathlib import Path

import typer

from database import init_database, seed_feeds
from helpers import load_urls

from ._common import emit_error, emit_json, require_db, status_msg

_MONITOR_DIR = Path(".monitor")


def _write_initial_monitor_report(seed_result: dict) -> None:
    """Create an initial monitor report after seeding.

    This ensures ``.monitor/latest-report.json`` exists when agents
    start their first cycle, preventing errors from agents that
    expect the file to be present.
    """
    _MONITOR_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "HEALTHY",
        "metrics": {
            "feeds_total": seed_result.get("seeded", 0),
            "download_backlog": 0,
            "parse_backlog": 0,
            "download_failures": 0,
            "parse_failures": 0,
            "parsed": 0,
        },
        "alerts": [],
        "recommendations": [
            "System freshly seeded. " "Run initial fetch cycle to populate articles."
        ],
    }
    report_path = _MONITOR_DIR / "latest-report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")


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

    result = {
        "seeded": count,
        "total_urls": len(urls),
        "skipped": len(urls) - count,
    }

    # Create initial monitor report so agents don't fail on missing file
    if count > 0:
        _write_initial_monitor_report(result)

    return result


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
