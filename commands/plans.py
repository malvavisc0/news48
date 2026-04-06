"""Plans command group - inspect and manage execution plans."""

import json
import sys
from typing import Any

import typer

from agents.tools.planner import (
    _ensure_plans_dir,
    _normalize_plan_for_consistency,
    _read_plan,
    _write_plan,
)

from ._common import emit_error, emit_json

plans_app = typer.Typer(help="Manage execution plans.")


def _iter_plans(status: str = "") -> list[dict]:
    plans_dir = _ensure_plans_dir()
    items = []
    for plan_file in plans_dir.glob("*.json"):
        try:
            plan = json.loads(plan_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if status and plan.get("status") != status.lower():
            continue
        items.append(plan)
    items.sort(key=lambda p: p.get("created_at", ""))
    return items


def _terminal_status_from_steps(plan: dict[str, Any]) -> str | None:
    """Return terminal plan status inferred from step statuses."""
    steps = plan.get("steps", [])
    if not steps:
        return None

    statuses = {s.get("status") for s in steps}
    if statuses.issubset({"completed"}):
        return "completed"
    if statuses.issubset({"completed", "failed"}):
        return "failed"
    return None


def _task_family(task: str) -> str:
    """Classify a task string into a coarse dedupe family."""
    t = (task or "").strip().lower()
    if "fetch" in t and "feed" in t:
        return "fetch"
    if "download" in t and "article" in t:
        return "download"
    if "parse" in t and "article" in t:
        return "parse"
    if "retry" in t and "article" in t:
        return "retry"
    if "fact-check" in t or "fact check" in t:
        return "fact-check"
    if "feed" in t and "stale" in t:
        return "feed-health"
    if "database" in t and ("health" in t or "integrity" in t):
        return "db-health"
    if "older than 48" in t or "retention" in t:
        return "retention"
    return t


def _remediate_plan(
    plan: dict[str, Any], parent_statuses: dict[str, str]
) -> list[str]:
    """Mutate a plan in-place to repair common planner/executor corruption."""
    actions: list[str] = []

    if _normalize_plan_for_consistency(plan):
        actions.append("normalized_status_mismatch")

    derived = _terminal_status_from_steps(plan)
    if derived and plan.get("status") != derived:
        plan["status"] = derived
        actions.append(f"set_plan_status={derived}")

    parent_id = plan.get("parent_id")
    if parent_id and parent_statuses.get(parent_id) == "completed":
        if plan.get("status") == "pending" and all(
            step.get("status") in {"completed", "failed"}
            for step in plan.get("steps", [])
        ):
            plan["status"] = derived or "completed"
            actions.append("closed_orphaned_child")

    return actions


def _dedupe_active_plans(plans: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """Fail newer duplicates in same family and parent scope."""
    active = [p for p in plans if p.get("status") in {"pending", "executing"}]
    active.sort(key=lambda p: p.get("created_at", ""))

    seen: dict[tuple[str, str | None], dict[str, Any]] = {}
    deduped: list[tuple[str, str]] = []
    for plan in active:
        key = (_task_family(plan.get("task", "")), plan.get("parent_id"))
        existing = seen.get(key)
        if not existing:
            seen[key] = plan
            continue

        if plan.get("id") == existing.get("id"):
            continue

        plan["status"] = "failed"
        plan["requeue_reason"] = (
            "Deduped active plan in same task family and parent scope"
        )
        deduped.append((plan["id"], existing["id"]))
    return deduped


@plans_app.command(name="list")
def plans_list(
    status: str = typer.Option("", "--status", "-s", help="Filter by status"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """List all plans, optionally filtered by status."""
    data = [
        {
            "plan_id": plan["id"],
            "task": plan["task"],
            "status": plan["status"],
            "parent_id": plan.get("parent_id"),
            "total_steps": len(plan.get("steps", [])),
            "created_at": plan.get("created_at"),
            "updated_at": plan.get("updated_at"),
        }
        for plan in _iter_plans(status=status)
    ]
    if output_json:
        json.dump(data, sys.stdout, default=str, indent=2)
        print()
        return
    for plan in data:
        print(
            f"{plan['plan_id']} [{plan['status']}] {plan['task']} "
            f"(steps={plan['total_steps']})"
        )


@plans_app.command(name="show")
def plans_show(
    plan_id: str = typer.Argument(..., help="Plan ID"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Show a full plan with all steps."""
    try:
        plan = _read_plan(plan_id)
    except FileNotFoundError:
        emit_error(f"Plan not found: {plan_id}", as_json=output_json)
        return

    if output_json:
        emit_json(plan)
        return

    print(f"Plan: {plan['id']}")
    print(f"Task: {plan['task']}")
    print(f"Status: {plan['status']}")
    print(f"Parent: {plan.get('parent_id')}")
    print("Success Conditions:")
    for condition in plan.get("success_conditions", []):
        print(f"  - {condition}")
    print("Steps:")
    for step in plan.get("steps", []):
        print(f"  - {step['id']} [{step['status']}] {step['description']}")


@plans_app.command(name="cancel")
def plans_cancel(
    plan_id: str = typer.Argument(..., help="Plan ID"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Cancel a plan by marking it as failed."""
    try:
        plan = _read_plan(plan_id)
    except FileNotFoundError:
        emit_error(f"Plan not found: {plan_id}", as_json=output_json)
        return

    plan["status"] = "failed"
    _write_plan(plan)

    if output_json:
        emit_json(plan)
        return
    print(f"Cancelled plan {plan_id}")


@plans_app.command(name="remediate")
def plans_remediate(
    apply: bool = typer.Option(False, "--apply", help="Persist changes"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Audit/repair plan corruption and dedupe active pipeline plans."""
    plans = _iter_plans()
    parent_statuses = {p["id"]: p.get("status", "") for p in plans}
    report: dict[str, Any] = {
        "total": len(plans),
        "modified": 0,
        "changes": [],
        "deduped": [],
        "apply": apply,
    }

    for plan in plans:
        actions = _remediate_plan(plan, parent_statuses)
        if not actions:
            continue
        report["modified"] += 1
        report["changes"].append({"plan_id": plan["id"], "actions": actions})
        if apply:
            _write_plan(plan)

    deduped = _dedupe_active_plans(plans)
    if deduped:
        for duplicate_id, survivor_id in deduped:
            report["deduped"].append(
                {
                    "duplicate_plan_id": duplicate_id,
                    "survivor_plan_id": survivor_id,
                }
            )
        if apply:
            by_id = {p["id"]: p for p in plans}
            for duplicate_id, _ in deduped:
                _write_plan(by_id[duplicate_id])

    if output_json:
        emit_json(report)
        return

    print(
        f"Remediation {'applied' if apply else 'preview'}: "
        f"{report['modified']} plans changed, "
        f"{len(report['deduped'])} duplicates identified"
    )
