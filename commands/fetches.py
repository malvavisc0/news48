"""Fetches sub-app - view fetch history."""

import typer

from database import init_database, list_fetches

from ._common import _fmt_date, emit_json, require_db

fetches_app = typer.Typer(help="View fetch history.")


@fetches_app.command(name="list")
def list_fetches_cmd(
    limit: int = typer.Option(20, "--limit", "-l", help="Number of fetches to show"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List recent fetch runs with details."""
    db_path = require_db()
    init_database(db_path)

    fetches = list_fetches(db_path, limit=limit)

    data = {
        "total": len(fetches),
        "limit": limit,
        "fetches": [
            {
                "id": f["id"],
                "started_at": f["started_at"],
                "completed_at": f["completed_at"],
                "status": f["status"],
                "feeds_fetched": f["feeds_fetched"],
                "articles_found": f["articles_found"],
            }
            for f in fetches
        ],
    }

    if output_json:
        emit_json(data)
    else:
        print(f"Fetches: {len(fetches)}")
        for f in data["fetches"]:
            started = _fmt_date(f["started_at"])
            completed = _fmt_date(f["completed_at"])
            print(f"  [{f['status']}] Fetch #{f['id']}")
            print(f"    Started:  {started}")
            print(f"    Completed: {completed}")
            print(f"    Feeds: {f['feeds_fetched']}, Articles: {f['articles_found']}")
