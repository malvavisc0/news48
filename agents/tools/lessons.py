"""Lessons learned system — save and load agent lessons."""

import re
from pathlib import Path

from ._helpers import _safe_json

_LESSONS_FILE = Path(__file__).parents[2] / ".lessons.md"

# Minimum number of leading words to match for near-duplicate detection.
_DEDUP_PREFIX_WORDS = 8

# Lessons shorter than this are almost certainly status noise, not insights.
_MIN_LESSON_LENGTH = 10


def _normalize_words(text: str) -> list[str]:
    """Lower-case, strip punctuation, split into words."""
    return re.sub(r"[^a-z0-9 ]", "", text.lower()).split()


def _is_near_duplicate(lesson: str, existing_bullets: list[str]) -> bool:
    """Return True if *lesson* shares its first N words with any existing entry.

    This catches lessons that differ only in specific numbers/IDs/timestamps
    but repeat the same structural insight.
    """
    words = _normalize_words(lesson)
    prefix = tuple(words[:_DEDUP_PREFIX_WORDS])
    if len(prefix) < _DEDUP_PREFIX_WORDS:
        # Very short lessons — fall back to exact match only.
        return False
    for existing in existing_bullets:
        existing_words = _normalize_words(existing)
        if tuple(existing_words[:_DEDUP_PREFIX_WORDS]) == prefix:
            return True
    return False


def _is_status_noise(lesson: str) -> bool:
    """Return True if the text looks like a status report, not a lesson.

    Status noise patterns:
    - "No X detected", "All X healthy", "No issues"
    - Bare metric snapshots without actionable insight
    - Very short generic statements
    """
    lowered = lesson.lower().strip()
    noise_patterns = [
        r"^no\s+\w+\s+(detected|found|issues)",
        r"^all\s+\w+\s+(are\s+)?(healthy|enabled|ok)",
        r"^system is empty",
        r"^database is empty",
        r"^no active plans",
        r"^no (fetches|articles|cleanup|agent|log|feed)\s+(issues|entries)",
        r"^no\s+\w+\s+issues detected",
    ]
    for pat in noise_patterns:
        if re.match(pat, lowered):
            return True
    return False


def save_lesson(
    reason: str,
    agent_name: str,
    category: str,
    lesson: str,
) -> str:
    """Save a lesson learned to .lessons.md.

    ## When to Use
    Use this tool when you discover something worth remembering:
    - Correct command syntax after a failed attempt
    - How a process or workflow actually operates
    - Patterns or best practices learned from experience
    - Feed-specific quirks or requirements
    - Error recovery techniques that worked

    ## Do NOT Save
    - Status reports or metric snapshots (e.g., "No issues detected")
    - Per-article fact-check verdicts (use `articles check` instead)
    - System state summaries with transient numbers

    ## Parameters
    - `reason` (str): Why this lesson is being saved
    - `agent_name` (str): Which agent learned this
      (executor, parser, sentinel, fact_checker)
    - `category` (str): Category for grouping
      (e.g., "Command Syntax", "Process Insights")
    - `lesson` (str): The lesson text — be specific and actionable

    ## Returns
    JSON with:
    - `result`: Confirmation message
    - `error`: Empty on success, or error description
    """
    try:
        # --- pre-flight checks ---
        if len(lesson.strip()) < _MIN_LESSON_LENGTH:
            return _safe_json(
                {
                    "result": "",
                    "error": (
                        "Lesson too short to be actionable "
                        f"({len(lesson.strip())} chars, min {_MIN_LESSON_LENGTH}). "
                        "Lessons must be specific and reusable insights."
                    ),
                }
            )

        if _is_status_noise(lesson):
            return _safe_json(
                {
                    "result": "",
                    "error": (
                        "Rejected: this looks like a status report, not a "
                        "reusable lesson. Lessons must be actionable insights "
                        "that help future runs, not transient system state."
                    ),
                }
            )

        content = ""
        if _LESSONS_FILE.exists():
            content = _LESSONS_FILE.read_text(encoding="utf-8")
        else:
            content = "# Lessons Learned\n\n"

        agent_section = f"## {agent_name}"
        category_section = f"### {category}"
        lesson_bullet = f"- {lesson}"

        # Check idempotency: skip if exact lesson line already exists
        if f"\n{lesson_bullet}\n" in f"\n{content}\n":
            return _safe_json(
                {
                    "result": (
                        f"Lesson already exists for " f"{agent_name}/{category}"
                    ),
                    "error": "",
                }
            )

        # Check near-duplicate: skip if first N words match an existing bullet
        existing_bullets = re.findall(r"^- (.+)$", content, re.MULTILINE)
        if _is_near_duplicate(lesson, existing_bullets):
            return _safe_json(
                {
                    "result": (
                        f"Near-duplicate lesson already exists for "
                        f"{agent_name}/{category}"
                    ),
                    "error": "",
                }
            )

        # Ensure agent section exists
        if agent_section not in content:
            content += f"\n{agent_section}\n\n"

        # Helper: find the agent block boundaries in content
        agent_pattern = rf"^{re.escape(agent_section)}\s*$"

        def _agent_bounds() -> tuple[int, int]:
            m = re.search(agent_pattern, content, re.MULTILINE)
            if not m:
                return 0, len(content)
            start = m.end()
            nxt = re.search(r"^##\s+\S+", content[start:], re.MULTILINE)
            end = start + nxt.start() if nxt else len(content)
            return start, end

        # Ensure category section exists under agent
        agent_start, agent_block_end = _agent_bounds()
        agent_block = content[agent_start:agent_block_end]

        if category_section not in agent_block:
            # Insert category section at end of agent block
            insert_pos = agent_block_end
            content = (
                content[:insert_pos].rstrip()
                + f"\n\n{category_section}\n\n"
                + content[insert_pos:]
            )
            # Recalculate bounds after insertion
            agent_start, agent_block_end = _agent_bounds()

        # Find category within the agent block and insert the lesson
        cat_pattern = rf"^{re.escape(category_section)}\s*$"
        cat_match = re.search(
            cat_pattern,
            content[agent_start:agent_block_end],
            re.MULTILINE,
        )
        if cat_match:
            cat_start = agent_start + cat_match.end()
            # Find next section (### or ##) within agent block
            next_cat = re.search(
                r"^(?:###|##)\s+",
                content[cat_start:agent_block_end],
                re.MULTILINE,
            )
            insert_pos = cat_start + next_cat.start() if next_cat else agent_block_end
            # Insert lesson before the next section
            content = (
                content[:insert_pos].rstrip()
                + f"\n{lesson_bullet}\n"
                + content[insert_pos:]
            )
        else:
            # Fallback: append at end
            content += f"\n{lesson_bullet}\n"

        _LESSONS_FILE.write_text(content, encoding="utf-8")

        return _safe_json(
            {
                "result": (
                    f"Lesson saved for "
                    f"{agent_name}/{category}: "
                    f"{lesson[:60]}..."
                ),
                "error": "",
            }
        )
    except Exception as exc:
        return _safe_json(
            {
                "result": "",
                "error": f"Failed to save lesson: {exc}",
            }
        )


def _load_lessons() -> str:
    """Load all lessons from .lessons.md.

    Returns the full file content wrapped in a lessons header,
    or empty string if no file exists.
    """
    if not _LESSONS_FILE.exists():
        return ""

    content = _LESSONS_FILE.read_text(encoding="utf-8")
    if not content.strip():
        return ""

    return f"<!-- LESSONS LEARNED -->\n\n{content}"
