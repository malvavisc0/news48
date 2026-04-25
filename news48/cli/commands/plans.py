"""Plans command group - inspect and manage execution plans."""

import json
import sys
from typing import Any

import typer

from news48.core.agents.tools.planner import (
    _derive_plan_status_from_steps,
    _normalize_plan_for_consistency,
    _read_plan,
    _task_family,
    _write_plan,
)
from news48.core.agents.tools.planner._db import db_iter_plans

from ._common import emit_error, emit_json

plans_app = typer.Typer(help="Inspect and manage agent execution plans.")


def _iter_plans(status: str = "") -> list[dict]:
    if status:
        items = db_iter_plans(status=status.lower())
    else:
        items = db_iter_plans()
    items.sort(key=lambda p: p.get("created_at", ""))
    return items


def _has_active_children(campaign_id: str, all_plans: list[dict[str, Any]]) -> bool:
    """Check whether a campaign has any active child plans.

    Checks both ``campaign_id`` and ``parent_id`` fields to find
    children linked through either the non-blocking grouping field
    or the blocking dependency field.
    """
    for p in all_plans:
        is_child = (
            p.get("campaign_id") == campaign_id or p.get("parent_id") == campaign_id
        )
        if is_child and p.get("status") in {
            "pending",
            "executing",
            "completed",
        }:
            return True
    return False


def _remediate_plan(
    plan: dict[str, Any],
    parent_statuses: dict[str, str],
    all_plans: list[dict[str, Any]] | None = None,
) -> list[str]:
    """Mutate a plan in-place to repair common corruption."""
    actions: list[str] = []

    if _normalize_plan_for_consistency(plan):
        actions.append("normalized_status_mismatch")

    derived = _derive_plan_status_from_steps(plan)
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

    # Clear parent_id if parent has failed - child can never be eligible
    if parent_id and parent_statuses.get(parent_id) == "failed":
        plan["parent_id"] = None
        actions.append("cleared_failed_parent")

    # Clear parent_id if parent is a pending campaign — campaigns
    # are never directly completed by the executor, so children
    # would be blocked forever.
    if parent_id and all_plans is not None:
        parent = next((p for p in all_plans if p.get("id") == parent_id), None)
        if (
            parent
            and parent.get("plan_kind") == "campaign"
            and parent.get("status") == "pending"
        ):
            plan["parent_id"] = None
            plan["campaign_id"] = plan.get("campaign_id") or parent_id
            actions.append("cleared_campaign_parent_deadlock")

    # Fail orphaned campaigns — campaigns with no active child plans
    if (
        plan.get("plan_kind") == "campaign"
        and plan.get("status") == "pending"
        and all_plans is not None
    ):
        campaign_id = plan.get("id", "")
        if campaign_id and not _has_active_children(campaign_id, all_plans):
            plan["status"] = "failed"
            plan["requeue_reason"] = "orphaned_campaign_no_children"
            actions.append("failed_orphaned_campaign")

    return actions


def _dedupe_active_plans(
    plans: list[dict[str, Any]],
) -> list[tuple[str, str]]:
    """Fail newer duplicates in same family and parent scope."""
    active = [p for p in plans if p.get("status") in {"pending", "executing"}]
    active.sort(key=lambda p: p.get("created_at", ""))

    seen: dict[tuple[str, str | None, str, str, str], dict[str, Any]] = {}
    deduped: list[tuple[str, str]] = []
    for plan in active:
        key = (
            _task_family(plan.get("task", "")),
            plan.get("parent_id"),
            plan.get("plan_kind", "execution"),
            plan.get("scope_type", ""),
            plan.get("scope_value", ""),
        )
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
    status: str = typer.Option(
        "",
        "--status",
        "-s",
        help="Filter by status: pending, executing, completed, failed",
    ),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """List all plans, optionally filtered by status.

    Plans are created by the sentinel agent to fix detected issues.
    The executor agent claims and executes pending plans.
    """
    data = [
        {
            "plan_id": plan["id"],
            "task": plan["task"],
            "plan_kind": plan.get("plan_kind", "execution"),
            "status": plan["status"],
            "parent_id": plan.get("parent_id"),
            "scope_type": plan.get("scope_type", ""),
            "scope_value": plan.get("scope_value", ""),
            "campaign_id": plan.get("campaign_id"),
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
    print(f"Kind: {plan.get('plan_kind', 'execution')}")
    print(f"Parent: {plan.get('parent_id')}")
    scope_type = plan.get("scope_type") or "-"
    scope_value = plan.get("scope_value") or "-"
    print(f"Scope: {scope_type}:{scope_value}")
    print(f"Campaign: {plan.get('campaign_id') or '-'}")
    print("Success Conditions:")
    for condition in plan.get("success_conditions", []):
        print(f"  - {condition}")
    print("Steps:")
    for step in plan.get("steps", []):
        print(f"  - {step['id']} [{step['status']}] " f"{step['description']}")


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
    """Audit/repair plan corruption and dedupe active plans."""
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
        actions = _remediate_plan(plan, parent_statuses, all_plans=plans)
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
