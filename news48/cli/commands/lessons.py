"""Lessons command group — view and manage agent lessons."""

import json
import sys

import typer

from news48.core.agents.tools.lessons import _get_conn, _is_status_noise, _read_lessons

from ._common import emit_error, emit_json

lessons_app = typer.Typer(help="View and manage agent lessons.")

AGENT_NAMES = ["executor", "parser", "sentinel", "fact_checker"]
AGENT_NAMES_STR = ", ".join(AGENT_NAMES)


@lessons_app.command(name="list")
def lessons_list(
    agent: str = typer.Option(
        None,
        "--agent",
        "-a",
        help=f"Filter by agent name ({AGENT_NAMES_STR}).",
    ),
    category: str = typer.Option(
        None,
        "--category",
        "-c",
        help="Filter by category (substring match).",
    ),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """List all lessons learned by agents."""
    lessons = _read_lessons()

    if not lessons:
        if output_json:
            emit_json({"lessons": [], "total": 0})
        else:
            print("No lessons found.")
        return

    # Apply filters
    if agent:
        agent_lower = agent.lower()
        lessons = [le for le in lessons if le.get("agent", "").lower() == agent_lower]

    if category:
        cat_lower = category.lower()
        lessons = [le for le in lessons if cat_lower in le.get("category", "").lower()]

    if output_json:
        emit_json({"lessons": lessons, "total": len(lessons)})
    else:
        if not lessons:
            print("No lessons match the given filters.")
            return

        current_agent = ""
        current_cat = ""
        for le in lessons:
            if le.get("agent", "") != current_agent:
                current_agent = le.get("agent", "")
                current_cat = ""
                print(f"\n  {current_agent}")
                print(f"  {'─' * len(current_agent)}")
            if le.get("category", "") != current_cat:
                current_cat = le.get("category", "")
                print(f"    [{current_cat}]")
            print(f"      • {le.get('lesson', '')}")

        print(
            f"\n  {len(lessons)} lesson(s) total.",
            file=sys.stderr,
        )


@lessons_app.command(name="add")
def lessons_add(
    agent: str = typer.Option(
        ...,
        "--agent",
        "-a",
        help=f"Agent name ({AGENT_NAMES_STR}).",
    ),
    category: str = typer.Option(
        ...,
        "--category",
        "-c",
        help='Category (e.g. "Command Syntax").',
    ),
    lesson: str = typer.Option(
        ...,
        "--lesson",
        "-l",
        help="The lesson text.",
    ),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Add a new lesson manually."""
    if agent.lower() not in AGENT_NAMES:
        emit_error(
            f"Invalid agent '{agent}'. " f"Must be one of: {', '.join(AGENT_NAMES)}",
            as_json=output_json,
        )
        return

    # Reuse the agent tool's save_lesson function
    from news48.core.agents.tools.lessons import save_lesson

    result_str = save_lesson(
        reason="manual CLI entry",
        agent_name=agent.lower(),
        category=category,
        lesson=lesson,
    )
    result = json.loads(result_str)

    if result.get("error"):
        emit_error(result["error"], as_json=output_json)

    if output_json:
        emit_json(result)
    else:
        print(result["result"])


def _read_lessons_with_ids() -> list[dict]:
    """Read lessons including their IDs for deletion."""
    try:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT id, agent, category, lesson, created_at "
            "FROM lessons ORDER BY created_at DESC"
        ).fetchall()
        return [dict(row) for row in rows]
    except Exception:
        return []


@lessons_app.command(name="purge")
def lessons_purge(
    agent: str = typer.Option(
        None,
        "--agent",
        "-a",
        help=f"Filter by agent name ({AGENT_NAMES_STR}).",
    ),
    dry_run: bool = typer.Option(
        True,
        "--dry-run/--no-dry-run",
        help="Preview what would be deleted (default: True).",
    ),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Purge bad lessons that look like status noise or article content.

    This removes lessons that match the _is_status_noise patterns,
    which includes article-specific content summaries.
    """
    lessons = _read_lessons_with_ids()

    if agent:
        agent_lower = agent.lower()
        lessons = [le for le in lessons if le.get("agent", "").lower() == agent_lower]

    to_delete = []
    to_keep = []
    for le in lessons:
        text = le.get("lesson", "")
        if _is_status_noise(text):
            to_delete.append(le)
        else:
            to_keep.append(le)

    if output_json:
        emit_json(
            {
                "dry_run": dry_run,
                "total_lessons": len(lessons),
                "to_delete": len(to_delete),
                "to_keep": len(to_keep),
                "deleted_lessons": to_delete if dry_run else [],
            }
        )
    else:
        print(f"Total lessons: {len(lessons)}")
        print(f"Would delete: {len(to_delete)}")
        print(f"Would keep: {len(to_keep)}")
        print()

        if to_delete:
            print("Lessons to delete:")
            for le in to_delete[:10]:
                text = le.get("lesson", "")
                preview = text[:120] + "..." if len(text) > 120 else text
                print(f"  - [{le.get('agent')}] {preview}")
            if len(to_delete) > 10:
                print(f"  ... and {len(to_delete) - 10} more")
            print()

    if not dry_run and to_delete:
        conn = _get_conn()
        ids_to_delete = [le["id"] for le in to_delete]
        if ids_to_delete:
            placeholders = ",".join("?" for _ in ids_to_delete)
            result = conn.execute(
                f"DELETE FROM lessons WHERE id IN ({placeholders})",
                ids_to_delete,
            )
            conn.commit()
            if not output_json:
                print(f"Deleted {result.rowcount} lessons.")
