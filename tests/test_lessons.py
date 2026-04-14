"""Tests for the lessons learned system."""

import json

import pytest

import config
from agents.tools.lessons import _load_lessons, save_lesson


@pytest.fixture
def tmp_lessons(tmp_path, monkeypatch):
    """Create a temporary lessons.json file for testing."""
    lessons_file = tmp_path / "lessons.json"
    monkeypatch.setattr(config, "LESSONS_FILE", lessons_file)
    yield lessons_file


def test_save_lesson_creates_file(tmp_lessons):
    """save_lesson creates data/lessons.json when it doesn't exist."""
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
    lessons = json.loads(tmp_lessons.read_text())
    assert len(lessons) == 1
    assert lessons[0]["agent"] == "executor"
    assert lessons[0]["category"] == "Command Syntax"
    assert lessons[0]["lesson"] == "Use --limit 50 for scoped downloads"


def test_save_lesson_appends_to_existing(tmp_lessons):
    """save_lesson appends to existing lessons."""
    tmp_lessons.write_text(
        json.dumps(
            [
                {
                    "agent": "planner",
                    "category": "Planning",
                    "lesson": "Plan first",
                }
            ]
        )
    )

    result = save_lesson(
        reason="test",
        agent_name="executor",
        category="Error Recovery",
        lesson="Retry with backoff works",
    )

    data = json.loads(result)
    assert data["error"] == ""
    lessons = json.loads(tmp_lessons.read_text())
    assert len(lessons) == 2
    # Existing content preserved
    assert lessons[0]["agent"] == "planner"
    assert lessons[0]["lesson"] == "Plan first"
    # New lesson appended
    assert lessons[1]["agent"] == "executor"
    assert lessons[1]["category"] == "Error Recovery"
    assert lessons[1]["lesson"] == "Retry with backoff works"


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
    # Verify no duplicate entries
    lessons = json.loads(tmp_lessons.read_text())
    matching = [le for le in lessons if le["lesson"] == "Date format is %d.%m.%Y"]
    assert len(matching) == 1


def test_load_lessons_returns_empty_when_no_file(tmp_path, monkeypatch):
    """_load_lessons returns empty string when no file exists."""
    monkeypatch.setattr(config, "LESSONS_FILE", tmp_path / "lessons.json")
    result = _load_lessons()
    assert result == ""


def test_load_lessons_returns_formatted_content(tmp_lessons):
    """_load_lessons returns lessons formatted as markdown."""
    tmp_lessons.write_text(
        json.dumps(
            [
                {
                    "agent": "executor",
                    "category": "Test",
                    "lesson": "Lesson one",
                }
            ]
        )
    )

    result = _load_lessons()
    assert "<!-- LESSONS LEARNED -->" in result
    assert "# Lessons Learned" in result
    assert "## executor" in result
    assert "- Lesson one" in result


def test_load_lessons_returns_empty_for_blank_file(tmp_lessons):
    """_load_lessons returns empty string for empty JSON array."""
    tmp_lessons.write_text("[]")
    result = _load_lessons()
    assert result == ""


def test_compose_agent_instructions_includes_lessons(
    tmp_lessons,
):
    """compose_agent_instructions includes lessons when file exists."""
    tmp_lessons.write_text(
        json.dumps(
            [
                {
                    "agent": "executor",
                    "category": "Test",
                    "lesson": "Always verify plan",
                }
            ]
        )
    )

    from agents.skills import compose_agent_instructions

    prompt = compose_agent_instructions("executor", {})
    assert "<!-- LESSONS LEARNED -->" in prompt
    assert "- Always verify plan" in prompt


def test_compose_agent_instructions_no_lessons_when_empty(tmp_path, monkeypatch):
    """compose_agent_instructions has no lessons section when no file."""
    monkeypatch.setattr(config, "LESSONS_FILE", tmp_path / "lessons.json")
    from agents.skills import compose_agent_instructions

    prompt = compose_agent_instructions("executor", {})
    assert "<!-- LESSONS LEARNED -->" not in prompt


def test_save_lesson_scoped_correctly(tmp_lessons):
    """save_lesson stores correct agent/category per entry."""
    tmp_lessons.write_text(
        json.dumps(
            [
                {
                    "agent": "planner",
                    "category": "Process Insights",
                    "lesson": "Plan first",
                },
                {
                    "agent": "executor",
                    "category": "Process Insights",
                    "lesson": "Execute second",
                },
            ]
        )
    )

    save_lesson(
        reason="test",
        agent_name="executor",
        category="Process Insights",
        lesson="Always verify output",
    )

    lessons = json.loads(tmp_lessons.read_text())
    new_entry = lessons[-1]
    assert new_entry["agent"] == "executor"
    assert new_entry["lesson"] == "Always verify output"
    # Original entries preserved
    assert lessons[0]["agent"] == "planner"
    assert lessons[1]["agent"] == "executor"
    assert lessons[1]["lesson"] == "Execute second"


def test_save_lesson_idempotency_no_false_positive(tmp_lessons):
    """save_lesson does not skip a different lesson."""
    save_lesson(
        reason="test",
        agent_name="executor",
        category="Command Syntax",
        lesson="Use --limit 50 for scoped downloads",
    )

    # A different, shorter lesson
    result = save_lesson(
        reason="test",
        agent_name="executor",
        category="Command Syntax",
        lesson="Use --limit 50",
    )

    data = json.loads(result)
    assert data["error"] == ""
    assert "already exists" not in data["result"]
    lessons = json.loads(tmp_lessons.read_text())
    texts = [le["lesson"] for le in lessons]
    assert "Use --limit 50 for scoped downloads" in texts
    assert "Use --limit 50" in texts
