"""Tests for the lessons learned system."""

import json
from unittest.mock import patch

import pytest

from agents.tools.lessons import _load_lessons, save_lesson


@pytest.fixture
def tmp_lessons(tmp_path):
    """Create a temporary .lessons.md file for testing."""
    lessons_file = tmp_path / ".lessons.md"
    with patch(
        "agents.tools.lessons._LESSONS_FILE",
        lessons_file,
    ):
        yield lessons_file


def test_save_lesson_creates_file(tmp_lessons):
    """save_lesson creates .lessons.md when it doesn't exist."""
    assert not tmp_lessons.exists()

    result = save_lesson(
        reason="test",
        agent_name="executor",
        category="Command Syntax",
        lesson="Use --limit 50 for scoped downloads",
    )

    data = json.loads(result)
    assert data["error"] == ""
    assert tmp_lessons.exists()
    content = tmp_lessons.read_text()
    assert "# Lessons Learned" in content
    assert "## executor" in content
    assert "### Command Syntax" in content
    assert "- Use --limit 50 for scoped downloads" in content


def test_save_lesson_creates_agent_section_and_category(tmp_lessons):
    """save_lesson creates agent section and category if missing."""
    tmp_lessons.write_text(
        "# Lessons Learned\n\n## planner\n\n### Planning\n- Plan first\n"
    )

    result = save_lesson(
        reason="test",
        agent_name="executor",
        category="Error Recovery",
        lesson="Retry with backoff works",
    )

    data = json.loads(result)
    assert data["error"] == ""
    content = tmp_lessons.read_text()
    assert "## executor" in content
    assert "### Error Recovery" in content
    assert "- Retry with backoff works" in content
    # Existing content preserved
    assert "## planner" in content
    assert "- Plan first" in content


def test_save_lesson_is_idempotent(tmp_lessons):
    """save_lesson skips if exact lesson already exists."""
    save_lesson(
        reason="test",
        agent_name="parser",
        category="Content Handling",
        lesson="Date format is %d.%m.%Y",
    )

    result = save_lesson(
        reason="test",
        agent_name="parser",
        category="Content Handling",
        lesson="Date format is %d.%m.%Y",
    )

    data = json.loads(result)
    assert "already exists" in data["result"]
    # Verify no duplicate bullets
    content = tmp_lessons.read_text()
    assert content.count("- Date format is %d.%m.%Y") == 1


def test_load_lessons_returns_empty_when_no_file(tmp_path):
    """_load_lessons returns empty string when no file exists."""
    with patch(
        "agents.tools.lessons._LESSONS_FILE",
        tmp_path / ".lessons.md",
    ):
        result = _load_lessons()
        assert result == ""


def test_load_lessons_returns_full_content(tmp_lessons):
    """_load_lessons returns full content wrapped in header."""
    tmp_lessons.write_text(
        "# Lessons Learned\n\n## executor\n\n### Test\n- Lesson one\n"
    )

    result = _load_lessons()
    assert "<!-- LESSONS LEARNED -->" in result
    assert "# Lessons Learned" in result
    assert "## executor" in result
    assert "- Lesson one" in result


def test_load_lessons_returns_empty_for_blank_file(tmp_lessons):
    """_load_lessons returns empty string for whitespace-only file."""
    tmp_lessons.write_text("   \n\n  ")
    result = _load_lessons()
    assert result == ""


def test_compose_agent_instructions_includes_lessons(tmp_lessons):
    """compose_agent_instructions includes lessons when file exists."""
    tmp_lessons.write_text(
        "# Lessons Learned\n\n## executor\n\n### Test\n- Always verify plan\n"
    )

    from agents.skills import compose_agent_instructions

    prompt = compose_agent_instructions("executor", {})
    assert "<!-- LESSONS LEARNED -->" in prompt
    assert "- Always verify plan" in prompt


def test_compose_agent_instructions_no_lessons_when_empty(tmp_path):
    """compose_agent_instructions has no lessons section when no file."""
    with patch(
        "agents.tools.lessons._LESSONS_FILE",
        tmp_path / ".lessons.md",
    ):
        from agents.skills import compose_agent_instructions

        prompt = compose_agent_instructions("executor", {})
        assert "<!-- LESSONS LEARNED -->" not in prompt


def test_save_lesson_scoped_to_agent_block(tmp_lessons):
    """save_lesson inserts under the correct agent when categories overlap."""
    # Both agents have the same category name
    tmp_lessons.write_text(
        "# Lessons Learned\n\n"
        "## planner\n\n"
        "### Process Insights\n"
        "- Plan first\n\n"
        "## executor\n\n"
        "### Process Insights\n"
        "- Execute second\n"
    )

    save_lesson(
        reason="test",
        agent_name="executor",
        category="Process Insights",
        lesson="Always verify output",
    )

    content = tmp_lessons.read_text()
    # The new lesson must appear in the executor section, not the planner one
    planner_idx = content.index("## planner")
    executor_idx = content.index("## executor")
    lesson_idx = content.index("- Always verify output")
    assert lesson_idx > executor_idx, "Lesson was inserted before the executor section"
    # Planner section should NOT contain the new lesson
    planner_block = content[planner_idx:executor_idx]
    assert "- Always verify output" not in planner_block


def test_save_lesson_idempotency_no_false_positive(tmp_lessons):
    """save_lesson does not skip a shorter lesson that is a substring of an existing one."""
    save_lesson(
        reason="test",
        agent_name="executor",
        category="Command Syntax",
        lesson="Use --limit 50 for scoped downloads",
    )

    # A different, shorter lesson that is a substring of the first
    result = save_lesson(
        reason="test",
        agent_name="executor",
        category="Command Syntax",
        lesson="Use --limit 50",
    )

    data = json.loads(result)
    assert data["error"] == ""
    assert "already exists" not in data["result"]
    content = tmp_lessons.read_text()
    assert "- Use --limit 50 for scoped downloads" in content
    assert "- Use --limit 50\n" in content
