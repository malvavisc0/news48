"""Plans command group - inspect and manage execution plans."""

import json
import sys

import typer

from agents.tools.planner import _ensure_plans_dir, _read_plan, _write_plan

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
