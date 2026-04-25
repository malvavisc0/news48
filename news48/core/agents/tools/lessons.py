"""Lessons learned system — save and load agent lessons."""

import fcntl
import json
import re
from pathlib import Path

from news48.core import config

from ._helpers import _safe_json

# Minimum number of leading words to match for near-duplicate detection.
_DEDUP_PREFIX_WORDS = 8

# Lessons shorter than this are almost certainly status noise, not insights.
_MIN_LESSON_LENGTH = 10

# Maximum number of lessons to keep (LRU eviction).
_MAX_LESSONS = 100


def _lessons_lock_path() -> Path:
    """Return the lock file path adjacent to lessons.json."""
    return config.LESSONS_FILE.with_suffix(".json.lock")


def _normalize_words(text: str) -> list[str]:
    """Lower-case, strip punctuation, split into words."""
    return re.sub(r"[^a-z0-9 ]", "", text.lower()).split()


def _is_near_duplicate(lesson: str, existing_lessons: list[str]) -> bool:
    """Return True if *lesson* shares its first N words with any entry.

    This catches lessons that differ only in specific numbers/IDs/timestamps
    but repeat the same structural insight.
    """
    words = _normalize_words(lesson)
    prefix = tuple(words[:_DEDUP_PREFIX_WORDS])
    if len(prefix) < _DEDUP_PREFIX_WORDS:
        # Very short lessons — fall back to exact match only.
        return False
    for existing in existing_lessons:
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
        r"^no (fetches|articles|cleanup|agent|log|feed)" r"\s+(issues|entries)",
        r"^no\s+\w+\s+issues detected",
    ]
    for pat in noise_patterns:
        if re.match(pat, lowered):
            return True
    return False


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


def _write_lessons(lessons: list[dict]) -> None:
    """Write lessons list to the JSON file."""
    config.LESSONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.LESSONS_FILE.write_text(
        json.dumps(lessons, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _lock_lessons():
    """Acquire an exclusive lock for lessons file read-modify-write.

    Returns a file descriptor that must be passed to _unlock_lessons().
    """
    lock_path = _lessons_lock_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_fd = open(lock_path, "w")
    fcntl.flock(lock_fd, fcntl.LOCK_EX)
    return lock_fd


def _unlock_lessons(lock_fd):
    """Release the lessons file lock."""
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
    finally:
        lock_fd.close()


def save_lesson(
    reason: str,
    agent_name: str,
    category: str,
    lesson: str,
) -> str:
    """Save a lesson learned to data/lessons.json.

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
    import time

    try:
        # --- pre-flight checks (outside lock - read-only) ---
        if len(lesson.strip()) < _MIN_LESSON_LENGTH:
            return _safe_json(
                {
                    "result": "",
                    "error": (
                        "Lesson too short to be actionable "
                        f"({len(lesson.strip())} chars, "
                        f"min {_MIN_LESSON_LENGTH}). "
                        "Lessons must be specific and "
                        "reusable insights."
                    ),
                }
            )

        if _is_status_noise(lesson):
            return _safe_json(
                {
                    "result": "",
                    "error": (
                        "Rejected: this looks like a status report, "
                        "not a reusable lesson. Lessons must be "
                        "actionable insights that help future runs, "
                        "not transient system state."
                    ),
                }
            )

        # --- critical section: read-check-write under lock ---
        lock_fd = _lock_lessons()
        try:
            lessons = _read_lessons()

            # Check idempotency: skip if exact lesson already exists
            for entry in lessons:
                if (
                    entry.get("agent") == agent_name
                    and entry.get("category") == category
                    and entry.get("lesson") == lesson
                ):
                    return _safe_json(
                        {
                            "result": (
                                f"Lesson already exists for " f"{agent_name}/{category}"
                            ),
                            "error": "",
                        }
                    )

            # Check near-duplicate
            existing_texts = [e.get("lesson", "") for e in lessons]
            if _is_near_duplicate(lesson, existing_texts):
                return _safe_json(
                    {
                        "result": (
                            f"Near-duplicate lesson already exists for "
                            f"{agent_name}/{category}"
                        ),
                        "error": "",
                    }
                )

            # Append with timestamp
            lessons.append(
                {
                    "agent": agent_name,
                    "category": category,
                    "lesson": lesson,
                    "created_at": time.time(),
                }
            )

            # LRU eviction: keep only the most recent _MAX_LESSONS
            if len(lessons) > _MAX_LESSONS:
                # Sort by created_at descending, keep top _MAX_LESSONS
                lessons.sort(key=lambda e: e.get("created_at", 0), reverse=True)
                lessons = lessons[:_MAX_LESSONS]

            _write_lessons(lessons)
        finally:
            _unlock_lessons(lock_fd)

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
    """Load all lessons from data/lessons.json.

    Returns the lessons formatted as markdown for agent instructions,
    or empty string if no lessons exist.
    """
    lessons = _read_lessons()
    if not lessons:
        return ""

    # Sort by recency (newest first) if timestamps available
    def _sort_key(entry: dict) -> float:
        return entry.get("created_at", 0)

    lessons_sorted = sorted(lessons, key=_sort_key, reverse=True)

    # Group by agent, then by category
    grouped: dict[str, dict[str, list[str]]] = {}
    for entry in lessons_sorted:
        agent = entry.get("agent", "unknown")
        cat = entry.get("category", "Uncategorized")
        text = entry.get("lesson", "")
        if not text:
            continue
        grouped.setdefault(agent, {}).setdefault(cat, []).append(text)

    # Format as readable text for agent context
    lines = ["<!-- LESSONS LEARNED -->", "", "# Lessons Learned", ""]
    for agent, categories in sorted(grouped.items()):
        lines.append(f"## {agent}")
        lines.append("")
        for cat, items in sorted(categories.items()):
            lines.append(f"### {cat}")
            for item in items:
                lines.append(f"- {item}")
            lines.append("")

    return "\n".join(lines)
