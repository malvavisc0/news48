"""Lessons learned system — save and load agent lessons."""

import re
import sqlite3

from news48.core import config

from ._helpers import _safe_json

# Minimum number of leading words to match for near-duplicate detection.
_DEDUP_PREFIX_WORDS = 8

# Lessons shorter than this are almost certainly status noise, not insights.
_MIN_LESSON_LENGTH = 10

# Maximum number of lessons to keep (LRU eviction).
_MAX_LESSONS = 100

# Module-level connection cache (one per process).
_conn: sqlite3.Connection | None = None


def _close_conn() -> None:
    """Close the cached SQLite connection and clear the cache."""
    global _conn
    if _conn is not None:
        try:
            _conn.close()
        except Exception:
            pass
        _conn = None


def _get_conn() -> sqlite3.Connection:
    """Return a shared sqlite3 connection to the lessons database.

    Opens (or reuses) a connection to ``config.LESSONS_DB``, enables WAL
    journal mode, sets a busy timeout, and ensures the ``lessons`` table
    and indexes exist.
    """
    global _conn
    if _conn is not None:
        return _conn

    config.LESSONS_DB.parent.mkdir(parents=True, exist_ok=True)
    _conn = sqlite3.connect(str(config.LESSONS_DB))
    _conn.row_factory = sqlite3.Row
    _conn.execute("PRAGMA journal_mode=WAL")
    _conn.execute("PRAGMA busy_timeout=5000")
    _conn.execute("""
        CREATE TABLE IF NOT EXISTS lessons (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            agent       TEXT    NOT NULL,
            category    TEXT    NOT NULL,
            lesson      TEXT    NOT NULL,
            created_at  REAL    NOT NULL
        )
        """)
    _conn.execute("CREATE INDEX IF NOT EXISTS idx_lessons_agent " "ON lessons(agent)")
    _conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_lessons_created_at " "ON lessons(created_at)"
    )
    _conn.commit()
    return _conn


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
    """Read lessons from the SQLite database.

    Returns an empty list if the database doesn't exist or is empty.
    """
    try:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT agent, category, lesson, created_at "
            "FROM lessons ORDER BY created_at DESC"
        ).fetchall()
        return [dict(row) for row in rows]
    except Exception:
        return []


def save_lesson(
    reason: str,
    agent_name: str,
    category: str,
    lesson: str,
) -> str:
    """Save a lesson learned to the lessons database.

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
        # --- pre-flight checks ---
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

        conn = _get_conn()

        # Check idempotency: skip if exact lesson already exists
        existing = conn.execute(
            "SELECT id FROM lessons " "WHERE agent = ? AND category = ? AND lesson = ?",
            (agent_name, category, lesson),
        ).fetchone()
        if existing:
            return _safe_json(
                {
                    "result": (
                        f"Lesson already exists for " f"{agent_name}/{category}"
                    ),
                    "error": "",
                }
            )

        # Check near-duplicate against existing lessons
        all_lessons = conn.execute("SELECT lesson FROM lessons").fetchall()
        existing_texts = [row["lesson"] for row in all_lessons]
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

        # Insert the new lesson
        conn.execute(
            "INSERT INTO lessons (agent, category, lesson, created_at) "
            "VALUES (?, ?, ?, ?)",
            (agent_name, category, lesson, time.time()),
        )

        # LRU eviction: keep only the most recent _MAX_LESSONS
        conn.execute(
            "DELETE FROM lessons WHERE id NOT IN "
            "(SELECT id FROM lessons ORDER BY created_at DESC LIMIT ?)",
            (_MAX_LESSONS,),
        )

        conn.commit()

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
    """Load all lessons from the lessons database.

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
