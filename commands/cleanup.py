"""Cleanup command - enforce 48-hour data retention policy."""

import typer

from database import (
    check_database_health,
    get_articles_older_than_hours,
    get_retention_policy_stats,
    init_database,
    purge_articles_older_than_hours,
)

from ._common import emit_error, emit_json, require_db

cleanup_app = typer.Typer(help="Manage data retention and cleanup.")


@cleanup_app.command(name="status")
def cleanup_status(
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show 48-hour retention policy status."""
    db_path = require_db()
    init_database(db_path)

    try:
        stats = get_retention_policy_stats(db_path)
    except Exception as e:
        emit_error(str(e), as_json=output_json)

    if output_json:
        emit_json(stats)
    else:
        print("Retention Policy Status (48-hour window)")
        print(f"  Total articles: {stats['total_articles']:,}")
        print(f"  Within 48h: {stats['articles_within_48h']:,}")
        print(f"  Expired (>48h): {stats['articles_expired']:,}")
        print(f"  Retention rate: {stats['retention_rate']}%")
        print(f"  Oldest article: {stats['oldest_article'] or 'N/A'}")
        print(f"  Newest article: {stats['newest_article'] or 'N/A'}")


@cleanup_app.command(name="purge")
def cleanup_purge(
    hours: int = typer.Option(48, "--hours", "-h", help="Hours threshold for purge"),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        "-n",
        help="Show what would be deleted without deleting",
    ),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Purge articles older than specified hours (default: 48)."""
    db_path = require_db()
    init_database(db_path)

    # Get articles that would be purged
    try:
        old_articles = get_articles_older_than_hours(db_path, hours)
    except Exception as e:
        emit_error(str(e), as_json=output_json)

    if not old_articles:
        if output_json:
            emit_json(
                {
                    "purged": 0,
                    "threshold_hours": hours,
                    "dry_run": dry_run,
                    "message": "No articles found older than threshold",
                }
            )
        else:
            print(f"No articles found older than {hours} hours")
        return

    # Show preview
    if not output_json and not dry_run:
        print(f"Found {len(old_articles)} articles older than {hours} hours:")
        for article in old_articles[:10]:  # Show first 10
            print(f"  - [{article['id']}] {article['title'] or 'Untitled'}")
            print(f"    Created: {article['created_at']}")
        if len(old_articles) > 10:
            print(f"  ... and {len(old_articles) - 10} more")
        print()

    # Confirm deletion
    if not force and not dry_run and not output_json:
        confirm = typer.confirm(
            f"Purge {len(old_articles)} articles older than {hours} hours?"
        )
        if not confirm:
            print("Purge cancelled")
            return

    # Execute purge
    try:
        result = purge_articles_older_than_hours(db_path, hours, dry_run)
    except Exception as e:
        emit_error(str(e), as_json=output_json)

    if output_json:
        emit_json(result)
    else:
        if dry_run:
            print(f"[DRY RUN] Would purge {result['articles_found']} articles")
        else:
            deleted = result["articles_deleted"]
            print(f"Purged {deleted} articles older than {hours} hours")


@cleanup_app.command(name="health")
def cleanup_health(
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Check database health and connectivity."""
    db_path = require_db()

    try:
        health = check_database_health(db_path)
    except Exception as e:
        emit_error(str(e), as_json=output_json)

    if output_json:
        emit_json(health)
    else:
        print("Database Health Check")
        print(f"  Connected: {'✓' if health['is_connected'] else '✗'}")
        print(f"  Size: {health['db_size_mb']} MB")
        print(f"  WAL mode: {'✓' if health['wal_mode'] else '✗'}")
        print(f"  Integrity: {'✓' if health['integrity_ok'] else '✗'}")
        print("  Table counts:")
        for table, count in health["table_counts"].items():
            print(f"    {table}: {count:,}")
