"""Lessons command group — view and manage agent lessons."""

import json
import re
import sys
from pathlib import Path

import typer

from ._common import emit_error, emit_json

lessons_app = typer.Typer(help="View and manage agent lessons.")

_LESSONS_FILE = Path(".lessons.md")

AGENT_NAMES = ["executor", "parser", "sentinel", "fact_checker"]


def _parse_lessons(
    content: str,
) -> list[dict]:
    """Parse .lessons.md into structured lesson entries.

    Returns a list of dicts with keys: agent, category, lesson.
    """
    lessons: list[dict] = []
    current_agent = ""
    current_category = ""

    for line in content.splitlines():
        line_stripped = line.strip()

        # Agent section: ## executor
        m = re.match(r"^##\s+(\S+.*)$", line_stripped)
        if m and not line_stripped.startswith("###"):
            current_agent = m.group(1).strip()
            current_category = ""
            continue

        # Category section: ### Command Syntax
        m = re.match(r"^###\s+(.+)$", line_stripped)
        if m:
            current_category = m.group(1).strip()
            continue

        # Lesson bullet: - lesson text
        m = re.match(r"^-\s+(.+)$", line_stripped)
        if m and current_agent:
            lessons.append(
                {
                    "agent": current_agent,
                    "category": current_category or "Uncategorized",
                    "lesson": m.group(1).strip(),
                }
            )

    return lessons


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
    if not _LESSONS_FILE.exists():
        if output_json:
            emit_json({"lessons": [], "total": 0})
        else:
            print("No lessons found (.lessons.md does not exist).")
        return

    content = _LESSONS_FILE.read_text(encoding="utf-8")
    if not content.strip():
        if output_json:
            emit_json({"lessons": [], "total": 0})
        else:
            print("No lessons found (.lessons.md is empty).")
        return

    lessons = _parse_lessons(content)

    # Apply filters
    if agent:
        agent_lower = agent.lower()
        lessons = [le for le in lessons if le["agent"].lower() == agent_lower]

    if category:
        cat_lower = category.lower()
        lessons = [le for le in lessons if cat_lower in le["category"].lower()]

    if output_json:
        emit_json({"lessons": lessons, "total": len(lessons)})
    else:
        if not lessons:
            print("No lessons match the given filters.")
            return

        current_agent = ""
        current_cat = ""
        for le in lessons:
            if le["agent"] != current_agent:
                current_agent = le["agent"]
                current_cat = ""
                print(f"\n  {current_agent}")
                print(f"  {'─' * len(current_agent)}")
            if le["category"] != current_cat:
                current_cat = le["category"]
                print(f"    [{current_cat}]")
            print(f"      • {le['lesson']}")

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
        help="Agent name (executor, parser, planner, monitor).",
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
    from agents.tools.lessons import save_lesson

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
