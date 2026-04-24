"""Seed command - seed the database with feed URLs from a file."""

import json
from datetime import datetime, timezone

import typer

from news48.core import config
from news48.core.database import seed_feeds
from news48.core.helpers.feed import load_urls

from ._common import emit_error, emit_json, require_db, status_msg


def _write_initial_monitor_report(seed_result: dict) -> None:
    """Create an initial monitor report after seeding.

    This ensures ``data/monitor/latest-report.json`` exists when agents
    start their first cycle, preventing errors from agents that
    expect the file to be present.
    """
    config.MONITOR_DIR.mkdir(parents=True, exist_ok=True)
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
    report_path = config.MONITOR_DIR / "latest-report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")


def _seed(seed_file: str) -> dict:
    """Seed the database with feed URLs from a file.

    Args:
        seed_file: Path to the seed file containing feed URLs.

    Returns:
        A dict with seeding results.
    """
    require_db()
    urls = load_urls(seed_file)

    status_msg(f"Seeding {len(urls)} feed URLs...")
    count = seed_feeds(urls)

    result = {
        "seeded": count,
        "total_urls": len(urls),
        "skipped": len(urls) - count,
    }

    # Create initial files so agents don't fail on missing files
    if count > 0:
        _write_initial_monitor_report(result)
        _ensure_lessons_file()

    return result


def _ensure_lessons_file() -> None:
    """Create data/lessons.json with an empty lessons array.

    Ensures the lessons file is present from the start so agents
    and CLI commands that read it don't encounter a missing file.
    """
    if not config.LESSONS_FILE.exists():
        config.LESSONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        config.LESSONS_FILE.write_text("[]\n", encoding="utf-8")


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
