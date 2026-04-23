"""Lessons command group — view and manage agent lessons."""

import json
import sys

import typer

from news48.core import config

from ._common import emit_error, emit_json

lessons_app = typer.Typer(help="View and manage agent lessons.")


AGENT_NAMES = ["executor", "parser", "sentinel", "fact_checker"]


def _read_lessons() -> list[dict]:
    """Read lessons from the JSON file.

    Returns an empty list if the file doesn't exist or is empty.
    """
    if not config.LESSONS_FILE.exists():
        return []
    try:
        content = config.LESSONS_FILE.read_text(encoding="utf-8")
        if not content.strip():
            return []
        data = json.loads(content)
        if isinstance(data, list):
            return data
        return []
    except (json.JSONDecodeError, OSError):
        return []


@lessons_app.command(name="list")
def lessons_list(
    agent: str = typer.Option(
        None,
        "--agent",
        "-a",
        help="Filter by agent name.",
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
        help="Agent name (executor, parser, sentinel, fact_checker).",
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
