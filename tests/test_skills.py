"""Tests for the skills architecture."""

import json
from pathlib import Path

import config
from agents.skills import (
    PLAN_FAMILY_SKILLS,
    SKILL_REGISTRY,
    SkillDef,
    _get_skills_for_agent,
    _skill_matches_condition,
    compose_agent_instructions,
)
from agents.tools import planner as planner_tools


def test_skill_registry_all_have_id():
    """Every skill in registry has matching id."""
    for skill_id, skill in SKILL_REGISTRY.items():
        assert skill.id == skill_id, f"Skill {skill_id} has mismatched id"


def test_skill_registry_all_have_valid_agents():
    """Every skill has valid agent list."""
    valid_agents = {"executor", "parser", "fact_checker", "sentinel"}
    for skill_id, skill in SKILL_REGISTRY.items():
        for agent in skill.agents:
            assert agent in valid_agents, f"Skill {skill_id} has invalid agent: {agent}"


def test_skill_registry_all_have_file():
    """Every skill has a non-empty file path."""
    for skill_id, skill in SKILL_REGISTRY.items():
        assert skill.file, f"Skill {skill_id} has empty file"
        assert skill.file.endswith(".md"), f"Skill {skill_id} file does not end in .md"


def test_skill_registry_no_duplicate_ids():
    """Registry has no duplicate skill IDs."""
    ids = list(SKILL_REGISTRY.keys())
    assert len(ids) == len(set(ids)), "Duplicate skill IDs found"


def test_plan_family_skills_covers_all_families():
    """PLAN_FAMILY_SKILLS covers all expected families."""
    expected_families = {
        "fetch",
        "download",
        "fact-check",
        "retention",
        "cleanup",
        "feed-health",
        "db-health",
        "retry",
    }
    assert set(PLAN_FAMILY_SKILLS.keys()) == expected_families


def test_plan_family_skills_values_are_valid_skill_ids():
    """PLAN_FAMILY_SKILLS values are valid skill IDs."""
    for family, skill_ids in PLAN_FAMILY_SKILLS.items():
        for skill_id in skill_ids:
            assert (
                skill_id in SKILL_REGISTRY
            ), f"Family {family} references unknown skill: {skill_id}"


def test_conditional_skills_have_condition_keys():
    """All conditional skills have non-empty condition_key."""
    for skill_id, skill in SKILL_REGISTRY.items():
        if not skill.always:
            assert (
                skill.condition_key
            ), f"Conditional skill {skill_id} missing condition_key"


def test_shared_skills_available_to_all_agents():
    """Shared skills available to all agents."""
    shared_skills = {
        "use-json-output",
        "gather-evidence",
        "verify-outcomes",
        "fail-safely",
    }
    all_agents = {"executor", "parser", "fact_checker", "sentinel"}
    for skill_id in shared_skills:
        skill = SKILL_REGISTRY[skill_id]
        assert (
            set(skill.agents) == all_agents
        ), f"Shared skill {skill_id} not available to all agents"


def test_skill_matches_condition_always_true():
    """Always skills match any condition."""
    skill = SkillDef(id="test", file="test.md", agents=("executor",), always=True)
    assert _skill_matches_condition(skill, {}) is True
    assert _skill_matches_condition(skill, {"any": "value"}) is True


def test_skill_matches_condition_simple_key():
    """Simple condition key matches truthy value."""
    skill = SkillDef(
        id="test",
        file="test.md",
        agents=("executor",),
        always=False,
        condition_key="backlog_high",
    )
    assert _skill_matches_condition(skill, {"backlog_high": True}) is True
    assert _skill_matches_condition(skill, {"backlog_high": False}) is False
    assert _skill_matches_condition(skill, {}) is False


def test_skill_matches_condition_compound_key():
    """Compound condition key (key:value) matches exact value."""
    skill = SkillDef(
        id="test",
        file="test.md",
        agents=("executor",),
        always=False,
        condition_key="plan_family:fact-check",
    )
    assert _skill_matches_condition(skill, {"plan_family": "fact-check"}) is True
    assert _skill_matches_condition(skill, {"plan_family": "download"}) is False
    assert _skill_matches_condition(skill, {}) is False


def test_skill_matches_condition_compound_key_or():
    """Compound condition key with pipe OR matches any listed value."""
    skill = SkillDef(
        id="test",
        file="test.md",
        agents=("sentinel",),
        always=False,
        condition_key="status:WARNING|CRITICAL",
    )
    assert _skill_matches_condition(skill, {"status": "WARNING"}) is True
    assert _skill_matches_condition(skill, {"status": "CRITICAL"}) is True
    assert _skill_matches_condition(skill, {"status": "HEALTHY"}) is False
    assert _skill_matches_condition(skill, {}) is False


def test_get_skills_for_agent_includes_always_on():
    """Always-on skills are included for their agents."""
    skills = set(_get_skills_for_agent("executor", {}))
    # Always-on executor skills
    always_on = [
        "use-json-output",
        "gather-evidence",
        "verify-outcomes",
        "fail-safely",
        "claim-plan",
        "manage-steps",
        "run-command",
        "verify-plan",
    ]
    for skill_id in always_on:
        assert (
            skill_id in skills
        ), f"Always-on skill {skill_id} not included for executor"


def test_get_skills_for_agent_excludes_other_agents():
    """Skills are only included for their designated agents."""
    skills = set(_get_skills_for_agent("executor", {}))
    # Parser-specific skills should not be included
    parser_skills = ["read-source", "extract-facts", "normalize-fields"]
    for skill_id in parser_skills:
        assert (
            skill_id not in skills
        ), f"Parser skill {skill_id} incorrectly included for executor"


def test_get_skills_for_agent_includes_conditional_when_matched():
    """Conditional skills are included when condition matches."""
    skills = set(_get_skills_for_agent("executor", {"plan_family": "fact-check"}))
    assert (
        "run-fact-check" in skills
    ), "run-fact-check should be included for fact-check family"


def test_get_skills_for_agent_excludes_conditional_when_not_matched():
    """Conditional skills are excluded when condition does not match."""
    skills = set(_get_skills_for_agent("executor", {"plan_family": "download"}))
    assert (
        "run-fact-check" not in skills
    ), "run-fact-check should not be included for download family"


def test_get_skills_for_agent_uses_plan_family_skills_for_download():
    """PLAN_FAMILY_SKILLS correctly loads run-waves for download family."""
    skills = set(_get_skills_for_agent("executor", {"plan_family": "download"}))
    assert "run-waves" in skills, (
        "run-waves should be included for download family " "via PLAN_FAMILY_SKILLS"
    )


def test_get_skills_for_agent_uses_plan_family_skills_for_cleanup():
    """PLAN_FAMILY_SKILLS correctly loads run-cleanup for cleanup family."""
    skills = set(_get_skills_for_agent("executor", {"plan_family": "cleanup"}))
    assert "run-cleanup" in skills, (
        "run-cleanup should be included for cleanup family " "via PLAN_FAMILY_SKILLS"
    )


def test_get_skills_for_agent_parser_preloads_runtime_branches():
    """Parser preloads type/failure branches resolved after source read."""
    skills = set(_get_skills_for_agent("parser", {}))
    assert "adapt-to-type" in skills
    assert "report-failure" in skills


def test_get_skills_for_agent_sentinel_includes_core_skills():
    """Sentinel includes the always-on sentinel skills."""
    skills = set(_get_skills_for_agent("sentinel", {}))
    for skill_id in {
        "sentinel-business-logic",
        "sentinel-feed-curation",
        "thresholds",
    }:
        assert skill_id in skills


def test_get_skills_for_agent_fact_checker_includes_core_skills():
    """Fact-checker includes the always-on fact-checker skills."""
    skills = set(_get_skills_for_agent("fact_checker", {}))
    for skill_id in {
        "fc-business-logic",
        "fc-extract-claims",
        "fc-search-evidence",
        "fc-record-verdict",
    }:
        assert skill_id in skills


def test_compose_returns_string():
    """compose_agent_instructions returns a string."""
    result = compose_agent_instructions("executor", {})
    assert isinstance(result, str)
    assert len(result) > 0


def test_compose_includes_base_prompt():
    """Composed prompt includes base prompt content."""
    result = compose_agent_instructions("executor", {})
    assert "Executor Agent" in result or "# Executor" in result
    assert "make as many calls as needed" in result


def test_compose_includes_skills_marker_when_skills_exist():
    """Composed prompt includes SKILLS marker when skills are added."""
    result = compose_agent_instructions("executor", {})
    assert "<!-- SKILLS -->" in result


def test_compose_includes_shared_skills():
    """Composed prompt includes shared skill content."""
    result = compose_agent_instructions("executor", {})
    # Shared skills should be in the output — check by heading
    assert "# Skill: Require JSON command output" in result
    assert "current default batch size is 50" in result


def test_compose_executor_with_fact_check_includes_run_fact_check():
    """Executor with fact-check plan_family includes run-fact-check skill."""
    result = compose_agent_instructions("executor", {"plan_family": "fact-check"})
    assert "# Skill: Execute fact-check plans" in result


def test_compose_executor_with_download_includes_run_waves():
    """Executor with download plan_family includes run-waves skill."""
    result = compose_agent_instructions("executor", {"plan_family": "download"})
    assert "# Skill: Execute work in waves" in result


def test_compose_executor_with_parse_includes_run_waves():
    """Executor with parse plan_family does not load parser-specific skills."""
    result = compose_agent_instructions("executor", {"plan_family": "parse"})
    assert "# Skill: Execute work in waves" not in result


def test_compose_executor_with_cleanup_includes_run_cleanup():
    """Executor with cleanup plan_family includes run-cleanup skill."""
    result = compose_agent_instructions("executor", {"plan_family": "cleanup"})
    assert "# Skill: Execute cleanup plans" in result


def test_compose_executor_with_fetch_excludes_run_fact_check():
    """Executor with fetch family does NOT load run-fact-check."""
    result = compose_agent_instructions("executor", {"plan_family": "fetch"})
    assert "# Skill: Execute fact-check plans" not in result


def test_compose_sentinel_loads_sentinel_skills():
    """Sentinel loads its always-on skills with empty context."""
    result = compose_agent_instructions("sentinel", {})
    assert "Sentinel Business Logic" in result
    assert "Feed Curation Rules" in result


def test_compose_fact_checker_loads_fact_checker_skills():
    """Fact-checker loads its always-on skills with empty context."""
    result = compose_agent_instructions("fact_checker", {})
    assert "Fact-Check Business Logic" in result
    assert "Extract Claims" in result


def test_compose_sentinel_appends_email_status():
    """Sentinel gets email availability appended to base prompt."""
    result = compose_agent_instructions("sentinel", {"email_configured": True})
    assert "Email delivery is available" in result

    result = compose_agent_instructions("sentinel", {"email_configured": False})
    assert "Email delivery is not configured" in result


def test_compose_parser_loads_all_parser_skills():
    """Parser loads all its always-on skills with empty context."""
    result = compose_agent_instructions("parser", {})
    assert "# Skill: Read the source before parsing" in result
    assert "# Skill: Adapt parsing to article type" in result


def test_executor_business_logic_matches_runtime_loading_notes():
    """Executor business-logic doc matches current runtime family behavior."""
    content = Path("agents/skills/executor/business-logic.md").read_text(
        encoding="utf-8"
    )
    assert "plan_family:fetch` or `plan_family:download" in content
    assert "Parse-family plans may still be executed" in content


def test_parser_business_logic_matches_caller_verification_model():
    """Parser business logic notes caller-owned persistence verification."""
    content = Path("agents/skills/parser/business-logic.md").read_text(encoding="utf-8")
    verify_skill = Path("agents/skills/parser/verify-result.md").read_text(
        encoding="utf-8"
    )
    assert "caller verifies the" in content
    assert "Do not run extra verification commands" in verify_skill


def test_base_prompt_sizes_are_reasonable(tmp_path, monkeypatch):
    """Base prompts should be under 2000 chars after rewriting."""
    # This test verifies the base prompts are slim
    from agents.skills import _SKILLS_DIR

    for agent in ["executor", "parser", "fact_checker", "sentinel"]:
        base_path = _SKILLS_DIR.parent / "instructions" / f"{agent}.md"
        if base_path.exists():
            content = base_path.read_text(encoding="utf-8")
            # Rough token estimate: 1 token ≈ 4 chars
            estimated_tokens = len(content) / 4
            assert estimated_tokens < 600, (
                f"Base prompt for {agent} is too large: "
                f"~{estimated_tokens:.0f} tokens (expected < 600)"
            )


def test_peek_next_plan_returns_family_for_pending_plan(tmp_path, monkeypatch):
    """peek_next_plan returns task family for oldest pending plan."""
    monkeypatch.setattr(config, "PLANS_DIR", tmp_path / ".plans")

    # Create a simple pending plan (no parent, no dedup issues)
    payload = json.loads(
        planner_tools.create_plan(
            reason="test plan for peek",
            task="Download articles from feeds",
            steps=["Download articles for parsing"],
            success_conditions=["Articles downloaded"],
        )
    )
    assert payload["error"] == "", f"Failed to create plan: {payload['error']}"

    family = planner_tools.peek_next_plan()
    assert family == "download", f"Expected 'download', got '{family}'"


def test_peek_next_plan_skips_blocked_pending(tmp_path, monkeypatch):
    """peek_next_plan skips pending plans whose parent is not completed."""
    monkeypatch.setattr(config, "PLANS_DIR", tmp_path / ".plans")

    # Create a pending plan with non-existent parent
    json.loads(
        planner_tools.create_plan(
            reason="test",
            task="Download articles",
            steps=["Download"],
            success_conditions=["Articles downloaded"],
            parent_id="nonexistent-parent",
        )
    )

    family = planner_tools.peek_next_plan()
    assert family is None, f"Expected None for blocked plan, got '{family}'"


def test_peek_next_plan_returns_none_when_no_pending(tmp_path, monkeypatch):
    """peek_next_plan returns None when no eligible pending plans exist."""
    monkeypatch.setattr(config, "PLANS_DIR", tmp_path / ".plans")

    # Create a plan with a non-existent parent (blocked)
    json.loads(
        planner_tools.create_plan(
            reason="test",
            task="Download articles",
            steps=["Download"],
            success_conditions=["Articles downloaded"],
            parent_id="nonexistent-parent-123",
        )
    )
    # This plan is created but blocked by parent_id

    family = planner_tools.peek_next_plan()
    assert family is None, f"Expected None for blocked plan, got '{family}'"


def test_peek_next_plan_orders_by_created_at(tmp_path, monkeypatch):
    """peek_next_plan returns oldest pending plan's family."""
    monkeypatch.setattr(config, "PLANS_DIR", tmp_path / ".plans")

    # Create older pending plan first
    planner_tools.create_plan(
        reason="test",
        task="Parse downloaded articles",
        steps=["Parse"],
        success_conditions=["Articles parsed"],
    )

    # Create newer pending plan
    planner_tools.create_plan(
        reason="test",
        task="Download articles",
        steps=["Download"],
        success_conditions=["Articles downloaded"],
    )

    family = planner_tools.peek_next_plan()
    # Oldest pending is "parse"
    assert family == "parse", f"Expected 'parse' (oldest), got '{family}'"
