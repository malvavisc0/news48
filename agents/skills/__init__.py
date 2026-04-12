"""Skills architecture for build-time prompt composition.

This module provides the skill registry and compose_agent_instructions()
function that assembles a tailored system prompt from base prompt + skill
files before an agent starts running.

## File Layout

    agents/skills/
    ├── __init__.py          # SKILL_REGISTRY, compose_agent_instructions()
    ├── shared/
    │   ├── system-overview.md
    │   ├── use-json-output.md
    │   ├── gather-evidence.md
    │   ├── verify-outcomes.md
    │   ├── fail-safely.md
    │   ├── thresholds.md
    │   ├── cli-reference-planner.md
    │   ├── cli-reference-executor.md
    │   ├── cli-reference-parser.md
    │   └── cli-reference-monitor.md
    ├── planner/
    │   ├── business-logic.md     # Mermaid diagram + skill reference
    │   ├── begin-planning-cycle.md
    │   ├── read-monitor-report.md
    │   ├── prioritize-goals.md
    │   ├── deduplicate-plans.md
    │   ├── read-db-state.md
    │   ├── write-conditions.md
    │   ├── build-plan.md
    │   ├── throughput-emergency.md
    │   ├── plan-fact-check.md
    │   ├── plan-retry.md
    │   └── remediate-stuck.md
    ├── executor/
    │   ├── business-logic.md     # Mermaid diagram + skill reference
    │   ├── claim-plan.md
    │   ├── manage-steps.md
    │   ├── run-command.md
    │   ├── verify-plan.md
    │   ├── run-waves.md
    │   ├── add-steps.md
    │   ├── run-fact-check.md
    │   ├── run-cleanup.md
    │   ├── run-feed-health.md
    │   ├── run-db-health.md
    │   └── run-retry.md
    ├── parser/
    │   ├── business-logic.md     # Mermaid diagram + skill reference
    │   ├── read-source.md
    │   ├── extract-facts.md
    │   ├── normalize-fields.md
    │   ├── rewrite-content.md
    │   ├── enforce-quality.md
    │   ├── stage-file.md
    │   ├── verify-result.md
    │   ├── adapt-to-type.md
    │   └── report-failure.md
    └── monitor/
        ├── business-logic.md     # Mermaid diagram + skill reference
        ├── begin-monitoring-cycle.md
        ├── evaluate-thresholds.md
        ├── compute-rates.md
        ├── generate-alerts.md
        ├── recommend-actions.md
        ├── review-fact-check.md
        ├── write-monitor-report.md
        ├── write-metrics-history.md
        └── send-email.md
"""

from dataclasses import dataclass
from os import getenv
from pathlib import Path


@dataclass(frozen=True)
class SkillDef:
    """Definition of a single skill file."""

    id: str
    file: str  # Relative to agents/skills/
    agents: tuple[str, ...]  # Which agents may use this skill
    always: bool  # True = always included, False = conditional
    condition_key: str = ""  # Key in task_context that enables this skill


# Plan-family to conditional skill mapping for executor
PLAN_FAMILY_SKILLS: dict[str, list[str]] = {
    "fetch": ["run-waves"],
    "download": ["run-waves"],
    "fact-check": ["run-fact-check"],
    "retention": ["run-cleanup"],
    "cleanup": ["run-cleanup"],
    "feed-health": ["run-feed-health"],
    "db-health": ["run-db-health"],
    "retry": ["run-retry"],
}


SKILL_REGISTRY: dict[str, SkillDef] = {
    # -------------------------------------------------------------------------
    # Shared skills (all agents always load these)
    # -------------------------------------------------------------------------
    "system-overview": SkillDef(
        id="system-overview",
        file="shared/system-overview.md",
        agents=("planner", "executor", "parser", "monitor"),
        always=True,
    ),
    "use-json-output": SkillDef(
        id="use-json-output",
        file="shared/use-json-output.md",
        agents=("planner", "executor", "parser", "monitor"),
        always=True,
    ),
    "cli-reference-planner": SkillDef(
        id="cli-reference-planner",
        file="shared/cli-reference-planner.md",
        agents=("planner",),
        always=True,
    ),
    "gather-evidence": SkillDef(
        id="gather-evidence",
        file="shared/gather-evidence.md",
        agents=("planner", "executor", "parser", "monitor"),
        always=True,
    ),
    "verify-outcomes": SkillDef(
        id="verify-outcomes",
        file="shared/verify-outcomes.md",
        agents=("planner", "executor", "parser", "monitor"),
        always=True,
    ),
    "fail-safely": SkillDef(
        id="fail-safely",
        file="shared/fail-safely.md",
        agents=("planner", "executor", "parser", "monitor"),
        always=True,
    ),
    "thresholds": SkillDef(
        id="thresholds",
        file="shared/thresholds.md",
        agents=("planner", "monitor"),
        always=True,
    ),
    "error-taxonomy": SkillDef(
        id="error-taxonomy",
        file="shared/error-taxonomy.md",
        agents=("planner", "executor", "parser", "monitor"),
        always=True,
    ),
    # -------------------------------------------------------------------------
    # Planner skills
    # -------------------------------------------------------------------------
    "begin-planning-cycle": SkillDef(
        id="begin-planning-cycle",
        file="planner/begin-planning-cycle.md",
        agents=("planner",),
        always=True,
    ),
    "read-monitor-report": SkillDef(
        id="read-monitor-report",
        file="planner/read-monitor-report.md",
        agents=("planner",),
        always=True,
    ),
    "prioritize-goals": SkillDef(
        id="prioritize-goals",
        file="planner/prioritize-goals.md",
        agents=("planner",),
        always=True,
    ),
    "write-conditions": SkillDef(
        id="write-conditions",
        file="planner/write-conditions.md",
        agents=("planner",),
        always=True,
    ),
    "build-plan": SkillDef(
        id="build-plan",
        file="planner/build-plan.md",
        agents=("planner",),
        always=True,
    ),
    "deduplicate-plans": SkillDef(
        id="deduplicate-plans",
        file="planner/deduplicate-plans.md",
        agents=("planner",),
        always=True,
    ),
    "throughput-emergency": SkillDef(
        id="throughput-emergency",
        file="planner/throughput-emergency.md",
        agents=("planner",),
        always=False,
        condition_key="backlog_high",
    ),
    "plan-fact-check": SkillDef(
        id="plan-fact-check",
        file="planner/plan-fact-check.md",
        agents=("planner",),
        always=False,
        condition_key="fact_check_backlog",
    ),
    "plan-retry": SkillDef(
        id="plan-retry",
        file="planner/plan-retry.md",
        agents=("planner",),
        always=False,
        condition_key="failed_backlog",
    ),
    "remediate-stuck": SkillDef(
        id="remediate-stuck",
        file="planner/remediate-stuck.md",
        agents=("planner",),
        always=False,
        condition_key="stale_plans",
    ),
    "business-logic-planner": SkillDef(
        id="business-logic-planner",
        file="planner/business-logic.md",
        agents=("planner",),
        always=True,
    ),
    # -------------------------------------------------------------------------
    # Executor skills
    # -------------------------------------------------------------------------
    "cli-reference-executor": SkillDef(
        id="cli-reference-executor",
        file="shared/cli-reference-executor.md",
        agents=("executor",),
        always=True,
    ),
    "claim-plan": SkillDef(
        id="claim-plan",
        file="executor/claim-plan.md",
        agents=("executor",),
        always=True,
    ),
    "manage-steps": SkillDef(
        id="manage-steps",
        file="executor/manage-steps.md",
        agents=("executor",),
        always=True,
    ),
    "run-command": SkillDef(
        id="run-command",
        file="executor/run-command.md",
        agents=("executor",),
        always=True,
    ),
    "verify-plan": SkillDef(
        id="verify-plan",
        file="executor/verify-plan.md",
        agents=("executor",),
        always=True,
    ),
    "run-waves": SkillDef(
        id="run-waves",
        file="executor/run-waves.md",
        agents=("executor",),
        always=False,
        condition_key="plan_family:fetch",
    ),
    "add-steps": SkillDef(
        id="add-steps",
        file="executor/add-steps.md",
        agents=("executor",),
        always=False,
        condition_key="plan_family:discovery",
    ),
    "run-fact-check": SkillDef(
        id="run-fact-check",
        file="executor/run-fact-check.md",
        agents=("executor",),
        always=False,
        condition_key="plan_family:fact-check",
    ),
    "run-cleanup": SkillDef(
        id="run-cleanup",
        file="executor/run-cleanup.md",
        agents=("executor",),
        always=False,
        condition_key="plan_family:retention",
    ),
    "run-feed-health": SkillDef(
        id="run-feed-health",
        file="executor/run-feed-health.md",
        agents=("executor",),
        always=False,
        condition_key="plan_family:feed-health",
    ),
    "run-db-health": SkillDef(
        id="run-db-health",
        file="executor/run-db-health.md",
        agents=("executor",),
        always=False,
        condition_key="plan_family:db-health",
    ),
    "run-retry": SkillDef(
        id="run-retry",
        file="executor/run-retry.md",
        agents=("executor",),
        always=False,
        condition_key="plan_family:retry",
    ),
    "business-logic-executor": SkillDef(
        id="business-logic-executor",
        file="executor/business-logic.md",
        agents=("executor",),
        always=True,
    ),
    # -------------------------------------------------------------------------
    # Parser skills
    # -------------------------------------------------------------------------
    "cli-reference-parser": SkillDef(
        id="cli-reference-parser",
        file="shared/cli-reference-parser.md",
        agents=("parser",),
        always=True,
    ),
    "read-source": SkillDef(
        id="read-source",
        file="parser/read-source.md",
        agents=("parser",),
        always=True,
    ),
    "extract-facts": SkillDef(
        id="extract-facts",
        file="parser/extract-facts.md",
        agents=("parser",),
        always=True,
    ),
    "normalize-fields": SkillDef(
        id="normalize-fields",
        file="parser/normalize-fields.md",
        agents=("parser",),
        always=True,
    ),
    "rewrite-content": SkillDef(
        id="rewrite-content",
        file="parser/rewrite-content.md",
        agents=("parser",),
        always=True,
    ),
    "enforce-quality": SkillDef(
        id="enforce-quality",
        file="parser/enforce-quality.md",
        agents=("parser",),
        always=True,
    ),
    "stage-file": SkillDef(
        id="stage-file",
        file="parser/stage-file.md",
        agents=("parser",),
        always=True,
    ),
    "verify-result": SkillDef(
        id="verify-result",
        file="parser/verify-result.md",
        agents=("parser",),
        always=True,
    ),
    # Parser intra-cycle branch skills: these are always preloaded via
    # runtime_branch_skills because their conditions (non_standard_type,
    # quality_gate_failure) are only discoverable after the agent starts
    # reading the source article or evaluating quality gates.
    "adapt-to-type": SkillDef(
        id="adapt-to-type",
        file="parser/adapt-to-type.md",
        agents=("parser",),
        always=True,
    ),
    "report-failure": SkillDef(
        id="report-failure",
        file="parser/report-failure.md",
        agents=("parser",),
        always=True,
    ),
    "business-logic-parser": SkillDef(
        id="business-logic-parser",
        file="parser/business-logic.md",
        agents=("parser",),
        always=True,
    ),
    # -------------------------------------------------------------------------
    # Monitor skills
    # -------------------------------------------------------------------------
    "cli-reference-monitor": SkillDef(
        id="cli-reference-monitor",
        file="shared/cli-reference-monitor.md",
        agents=("monitor",),
        always=True,
    ),
    "begin-monitoring-cycle": SkillDef(
        id="begin-monitoring-cycle",
        file="monitor/begin-monitoring-cycle.md",
        agents=("monitor",),
        always=True,
    ),
    "compute-rates": SkillDef(
        id="compute-rates",
        file="monitor/compute-rates.md",
        agents=("monitor",),
        always=True,
    ),
    "evaluate-thresholds": SkillDef(
        id="evaluate-thresholds",
        file="monitor/evaluate-thresholds.md",
        agents=("monitor",),
        always=True,
    ),
    "review-fact-check": SkillDef(
        id="review-fact-check",
        file="monitor/review-fact-check.md",
        agents=("monitor",),
        always=True,
    ),
    "write-monitor-report": SkillDef(
        id="write-monitor-report",
        file="monitor/write-monitor-report.md",
        agents=("monitor",),
        always=True,
    ),
    "write-metrics-history": SkillDef(
        id="write-metrics-history",
        file="monitor/write-metrics-history.md",
        agents=("monitor",),
        always=True,
    ),
    "generate-alerts": SkillDef(
        id="generate-alerts",
        file="monitor/generate-alerts.md",
        agents=("monitor",),
        always=False,
        condition_key="threshold_breached",
    ),
    "recommend-actions": SkillDef(
        id="recommend-actions",
        file="monitor/recommend-actions.md",
        agents=("monitor",),
        always=False,
        condition_key="alerts_exist",
    ),
    "send-email": SkillDef(
        id="send-email",
        file="monitor/send-email.md",
        agents=("monitor",),
        always=False,
        condition_key="status:WARNING|CRITICAL",
    ),
    "business-logic-monitor": SkillDef(
        id="business-logic-monitor",
        file="monitor/business-logic.md",
        agents=("monitor",),
        always=True,
    ),
}


_SKILLS_DIR = Path(__file__).parent


def _read_skill_file(relative_path: str) -> str:
    """Read a skill markdown file and return its content."""
    skill_path = _SKILLS_DIR / relative_path
    if not skill_path.exists():
        return f"<!-- Skill file not found: {relative_path} -->"
    return skill_path.read_text(encoding="utf-8")


def _skill_matches_condition(skill: SkillDef, task_context: dict) -> bool:
    """Check if a conditional skill matches task_context."""
    if skill.always:
        return True

    condition_key = skill.condition_key
    if not condition_key:
        return False

    # Handle compound keys like "plan_family:fact-check" or
    # "status:WARNING|CRITICAL" (pipe = OR).
    if ":" in condition_key:
        key, expected_value = condition_key.split(":", 1)
        actual_value = str(task_context.get(key, ""))
        if "|" in expected_value:
            return actual_value in expected_value.split("|")
        return actual_value == expected_value

    # Simple boolean key
    return bool(task_context.get(condition_key))


def _get_skills_for_agent(agent_name: str, task_context: dict) -> list[str]:
    """Get skill IDs to include for an agent given task context.

    For executor agents, PLAN_FAMILY_SKILLS is consulted to resolve
    which conditional skills match the current plan family.  This is
    the authoritative mapping — individual condition_key values on
    SkillDefs are a fallback for non-family conditions.

    Planner, parser, and monitor agents also preload intra-cycle branch
    skills whose trigger is discovered only after the run starts (for
    example, after gathering evidence or reading the source article).
    """
    runtime_branch_skills: dict[str, set[str]] = {
        "planner": {
            "throughput-emergency",
            "plan-fact-check",
            "plan-retry",
            "remediate-stuck",
        },
        "parser": {"adapt-to-type", "report-failure"},
        "monitor": {"generate-alerts", "recommend-actions"},
    }

    # Resolve family-based conditional skills via PLAN_FAMILY_SKILLS
    family_skills: set[str] = set()
    plan_family = task_context.get("plan_family", "")
    if plan_family:
        family_skills.update(PLAN_FAMILY_SKILLS.get(plan_family, []))

    skill_ids = []
    for skill_id, skill in SKILL_REGISTRY.items():
        if agent_name not in skill.agents:
            continue
        if skill.always:
            skill_ids.append(skill_id)
        elif skill_id in family_skills:
            skill_ids.append(skill_id)
        elif skill_id == "send-email":
            if task_context.get("email_configured") and (
                "status" not in task_context
                or _skill_matches_condition(skill, task_context)
            ):
                skill_ids.append(skill_id)
        elif skill_id in runtime_branch_skills.get(agent_name, set()):
            skill_ids.append(skill_id)
        elif _skill_matches_condition(skill, task_context):
            skill_ids.append(skill_id)
    return skill_ids


def _email_is_configured() -> bool:
    """Return True when monitor email delivery is fully configured."""
    return bool(
        getenv("SMTP_HOST", "")
        and getenv("SMTP_USER", "")
        and getenv("SMTP_PASS", "")
        and getenv("MONITOR_EMAIL_TO", "")
    )


def compose_agent_instructions(
    agent_name: str,
    task_context: dict,
) -> str:
    """Compose a tailored system prompt from base prompt + skill files.

    Args:
        agent_name: One of planner, executor, parser, monitor.
        task_context: Dict with keys like plan_family, backlog_high,
            alerts_exist, etc. Used to conditionally include skills.

    Returns:
        A single string containing the composed system prompt.
    """
    ctx = dict(task_context)
    if agent_name == "monitor":
        ctx.setdefault("email_configured", _email_is_configured())

    # 1. Read base prompt
    base_prompt_path = _SKILLS_DIR.parent / "instructions" / f"{agent_name}.md"
    if base_prompt_path.exists():
        base_prompt = base_prompt_path.read_text(encoding="utf-8")
    else:
        base_prompt = (
            f"# {agent_name.capitalize()} Agent\n\n(No base prompt found.)"
        )

    if agent_name == "monitor":
        if ctx.get("email_configured"):
            base_prompt = (
                base_prompt.rstrip()
                + "\n\nEmail delivery is available in this environment."
            )
        else:
            base_prompt = (
                base_prompt.rstrip()
                + "\n\nEmail delivery is not configured in this environment. "
                + "Do not attempt to send email."
            )

    # 2. Get skill IDs to include
    skill_ids = _get_skills_for_agent(agent_name, ctx)

    # 3. Read and concatenate skill files
    skill_contents: list[str] = []
    for skill_id in skill_ids:
        skill = SKILL_REGISTRY[skill_id]
        content = _read_skill_file(skill.file)
        skill_contents.append(content)

    # 4. Assemble final prompt
    parts = [base_prompt]
    if skill_contents:
        parts.append("")
        parts.append("<!-- SKILLS -->")
        parts.extend(skill_contents)

    return "\n\n".join(parts)
