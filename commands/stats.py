"""Stats command - show system statistics."""

import json
import os
import sqlite3
from pathlib import Path

import typer
from rich.table import Table

from database import (
    get_article_stats,
    get_feed_stats,
    get_run_stats,
    init_database,
)

from ._common import _fmt_date, console, require_db


def _format_size(size_bytes: int) -> str:
    """Format a byte count as a human-readable size string."""
    if size_bytes > 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    if size_bytes > 1024:
        return f"{size_bytes / 1024:.2f} KB"
    return f"{size_bytes} bytes"


def _safe_int(value: int | float | str | None) -> int:
    """Coerce a value to int, defaulting to 0 for None."""
    if value is None:
        return 0
    return int(value)


def _collect_stats(db_path: Path, stale_days: int) -> dict:
    """Gather all stats into a single dict.

    Args:
        db_path: Path to the SQLite database file.
        stale_days: Days before a feed is considered stale.

    Returns:
        A dict containing database, articles, feeds, and runs stats.
    """
    db_size = os.path.getsize(db_path)

    article = get_article_stats(db_path)
    feed = get_feed_stats(db_path, stale_days)
    run = get_run_stats(db_path)

    return {
        "database": {
            "path": str(db_path),
            "size_bytes": db_size,
            "size_human": _format_size(db_size),
        },
        "articles": {
            "total": _safe_int(article["total"]),
            "parsed": _safe_int(article["parsed"]),
            "unparsed": _safe_int(article["unparsed"]),
            "no_content": _safe_int(article["no_content"]),
            "download_failures": _safe_int(article["download_failed"]),
            "parse_failures": _safe_int(article["parse_failed"]),
            "download_backlog": _safe_int(article["download_backlog"]),
            "parse_backlog": _safe_int(article["parse_backlog"]),
            "articles_today": _safe_int(article["articles_today"]),
            "articles_this_week": _safe_int(article["articles_this_week"]),
            "oldest_unparsed_at": article.get("oldest_unparsed_at"),
        },
        "sentiment": {
            "positive": _safe_int(article["sentiment_positive"]),
            "negative": _safe_int(article["sentiment_negative"]),
            "neutral": _safe_int(article["sentiment_neutral"]),
        },
        "feeds": {
            "total": _safe_int(feed["total"]),
            "never_fetched": _safe_int(feed["never_fetched"]),
            "stale": _safe_int(feed["stale"]),
            "stale_days": stale_days,
            "top_feeds": feed.get("top_feeds", []),
        },
        "runs": {
            "total": _safe_int(run["total_runs"]),
            "last_run_at": run.get("last_run_at"),
            "avg_articles_per_run": run.get("avg_articles_per_run"),
            "recent": run.get("recent_runs", []),
        },
    }


def _render_rich(data: dict) -> None:
    """Render stats as Rich tables and panels.

    Args:
        data: The stats dict from _collect_stats.
    """
    db = data["database"]
    art = data["articles"]
    sent = data["sentiment"]
    feeds = data["feeds"]
    runs = data["runs"]

    # ── Database ──────────────────────────────────────────
    tbl = Table(title="Database", show_header=False, min_width=40)
    tbl.add_column("Metric", style="bold")
    tbl.add_column("Value")
    tbl.add_row("Path", db["path"])
    tbl.add_row("Size", db["size_human"])
    console.print(tbl)

    # ── Articles ──────────────────────────────────────────
    tbl = Table(title="Articles", show_header=False, min_width=40)
    tbl.add_column("Metric", style="bold")
    tbl.add_column("Value", justify="right")
    tbl.add_row("Total", f"{art['total']:,}")
    tbl.add_row("Parsed", f"[green]{art['parsed']:,}[/green]")
    tbl.add_row("Unparsed", f"{art['unparsed']:,}")
    tbl.add_row("No content", f"{art['no_content']:,}")
    tbl.add_row(
        "Download failures",
        (
            f"[red]{art['download_failures']:,}[/red]"
            if art["download_failures"]
            else "0"
        ),
    )
    tbl.add_row(
        "Parse failures",
        (
            f"[red]{art['parse_failures']:,}[/red]"
            if art["parse_failures"]
            else "0"
        ),
    )
    tbl.add_row("New today", f"{art['articles_today']:,}")
    tbl.add_row("New this week", f"{art['articles_this_week']:,}")
    console.print(tbl)

    # ── Pipeline Health ───────────────────────────────────
    tbl = Table(
        title="Pipeline Health",
        show_header=False,
        min_width=40,
    )
    tbl.add_column("Metric", style="bold")
    tbl.add_column("Value", justify="right")
    tbl.add_row(
        "Download backlog",
        (
            f"[yellow]{art['download_backlog']:,}[/yellow]"
            if art["download_backlog"]
            else "[green]0[/green]"
        ),
    )
    tbl.add_row(
        "Parse backlog",
        (
            f"[yellow]{art['parse_backlog']:,}[/yellow]"
            if art["parse_backlog"]
            else "[green]0[/green]"
        ),
    )
    oldest = art.get("oldest_unparsed_at")
    tbl.add_row(
        "Oldest unparsed",
        _fmt_date(oldest) if oldest else "[green]—[/green]",
    )
    console.print(tbl)

    total_sent = sent["positive"] + sent["negative"] + sent["neutral"]
    if total_sent > 0:
        tbl = Table(
            title="Sentiment Distribution",
            show_header=False,
            min_width=40,
        )
        tbl.add_column("Sentiment", style="bold")
        tbl.add_column("Count", justify="right")
        tbl.add_column("%", justify="right")
        tbl.add_row(
            "Positive",
            f"[green]{sent['positive']:,}[/green]",
            f"{sent['positive'] / total_sent * 100:.1f}%",
        )
        tbl.add_row(
            "Negative",
            f"[red]{sent['negative']:,}[/red]",
            f"{sent['negative'] / total_sent * 100:.1f}%",
        )
        tbl.add_row(
            "Neutral",
            f"{sent['neutral']:,}",
            f"{sent['neutral'] / total_sent * 100:.1f}%",
        )
        console.print(tbl)

    tbl = Table(title="Feeds", show_header=False, min_width=40)
    tbl.add_column("Metric", style="bold")
    tbl.add_column("Value", justify="right")
    tbl.add_row("Total", f"{feeds['total']:,}")
    tbl.add_row(
        "Never fetched",
        (
            f"[yellow]{feeds['never_fetched']:,}[/yellow]"
            if feeds["never_fetched"]
            else "0"
        ),
    )
    tbl.add_row(
        f"Stale (>{feeds['stale_days']}d)",
        f"[red]{feeds['stale']:,}[/red]" if feeds["stale"] else "0",
    )
    console.print(tbl)

    top = feeds.get("top_feeds", [])
    if top:
        tbl = Table(title="Top Feeds by Article Count")
        tbl.add_column("#", justify="right", style="dim")
        tbl.add_column("Articles", justify="right", style="cyan")
        tbl.add_column("Title", style="green")
        tbl.add_column("URL", style="dim")
        for i, f in enumerate(top, 1):
            title = f.get("title") or "Untitled"
            url = f.get("url", "")
            count = _safe_int(f.get("article_count"))
            # Truncate with ellipsis for readability
            if len(title) > 50:
                title = title[:47] + "…"
            if len(url) > 50:
                url = url[:47] + "…"
            tbl.add_row(str(i), f"{count:,}", title, url)
        console.print(tbl)

    tbl = Table(title="Runs", show_header=False, min_width=40)
    tbl.add_column("Metric", style="bold")
    tbl.add_column("Value", justify="right")
    tbl.add_row("Total runs", f"{runs['total']:,}")
    tbl.add_row("Last run", _fmt_date(runs.get("last_run_at")))
    avg = runs.get("avg_articles_per_run")
    tbl.add_row(
        "Avg articles/run",
        str(avg) if avg is not None else "—",
    )
    console.print(tbl)

    recent = runs.get("recent", [])
    if recent:
        tbl = Table(title="Recent Runs")
        tbl.add_column("ID", justify="right", style="cyan")
        tbl.add_column("Started", style="dim")
        tbl.add_column("Status")
        tbl.add_column("Feeds", justify="right")
        tbl.add_column("Articles", justify="right")
        for r in recent:
            status = r.get("status", "unknown")
            style_map = {
                "completed": "green",
                "running": "yellow",
                "failed": "red",
            }
            st = style_map.get(status, "white")
            icon = {"completed": "✓", "failed": "✗"}.get(status, "…")
            tbl.add_row(
                str(r.get("id", "?")),
                _fmt_date(r.get("started_at")),
                f"[{st}]{icon} {status}[/{st}]",
                str(r.get("feeds_fetched", 0)),
                str(r.get("articles_found", 0)),
            )
        console.print(tbl)


def stats(
    output_json: bool = typer.Option(
        False,
        "--json",
        help="Output stats as JSON for scripting",
    ),
    stale_days: int = typer.Option(
        7,
        "--stale-days",
        help="Days before a feed is considered stale",
    ),
) -> None:
    """Show system statistics.

    Displays database size, article counts, pipeline health,
    sentiment distribution, feed statistics, and recent run
    history.
    """
    db_path = require_db()
    init_database(db_path)

    try:
        data = _collect_stats(db_path, stale_days)
    except sqlite3.DatabaseError as exc:
        console.print(f"[red]Database error: {exc}[/red]")
        raise typer.Exit(code=1) from exc

    if output_json:
        console.print_json(json.dumps(data, default=str))
    else:
        _render_rich(data)
