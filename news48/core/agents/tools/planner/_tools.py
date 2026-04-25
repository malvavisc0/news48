"""Public planner tool functions: create, update, claim, list, recover."""

import os
import uuid

from .._helpers import _safe_json
from ._constants import _TERMINAL_PLAN_STATUSES
from ._db import db_claim_plan, db_iter_plans, db_read_plan
from ._lifecycle import (
    _derive_plan_status_from_steps,
    _find_active_duplicate_plan,
    _infer_parent_plan_id,
    _is_plan_stale,
    _normalize_plan_for_consistency,
    _requeue_stale_plan,
    _task_family,
)
from ._storage import (
    _no_eligible_plans_response,
    _now,
    _read_plan,
    _serialize_plan,
    _write_plan,
)


def create_plan(
    reason: str,
    task: str,
    steps: list[str],
    success_conditions: list[str],
    parent_id: str = "",
    plan_kind: str = "execution",
    scope_type: str = "",
    scope_value: str = "",
    campaign_id: str = "",
) -> str:
    """Create a new execution plan, persist to the plans database.

    ## When to Use
    Use this tool when you need to break down a complex task into ordered
    steps that can be tracked and managed. Required before using
    `update_plan`.

    ## Why to Use
    - Track progress through multi-step workflows
    - Maintain state across agent interactions and restarts
    - Record results for each step individually
    - Plans are persisted to database and survive process exits

    ## Parameters
    - `reason` (str): Why planning is needed for this task
    - `task` (str): Overall task description (required, non-empty)
    - `steps` (list[str]): Ordered list of step descriptions
    - `success_conditions` (list[str]): Non-empty list of verifiable outcome
      statements. Each condition must describe an outcome (not an action)
      that can be verified using CLI commands like `news48 ... --json`.
    - `parent_id` (str): Optional parent plan ID for sequencing
    - `plan_kind` (str): Optional plan type: `execution` or `campaign`
    - `scope_type` (str): Optional scope key, e.g. `feed`
    - `scope_value` (str): Optional scope value, e.g. a feed domain
    - `campaign_id` (str): Optional grouping plan ID for related child plans

    ## Validation
    - `task` must be a non-empty string (whitespace-only is rejected)
    - `success_conditions` must be a non-empty list
    - Each condition must be a non-empty string (blank entries rejected)

    ## Returns
    JSON with:
    - `result`: Plan object with id, task, success_conditions, steps, progress
    - `error`: Empty on success, or validation error message
    """
    try:
        # Validate task
        if not task or not task.strip():
            return _safe_json(
                {
                    "result": "",
                    "error": "task is required and must be non-empty",
                }
            )

        # Validate success_conditions
        if not success_conditions:
            return _safe_json({"result": "", "error": "success_conditions is required"})

        for i, condition in enumerate(success_conditions):
            if not isinstance(condition, str):
                return _safe_json(
                    {
                        "result": "",
                        "error": f"success_conditions[{i}] must be a string",
                    }
                )
            if not condition.strip():
                return _safe_json(
                    {
                        "result": "",
                        "error": (f"success_conditions[{i}] cannot be blank"),
                    }
                )

        normalized_plan_kind = (plan_kind or "execution").strip().lower()
        if normalized_plan_kind not in {"execution", "campaign"}:
            return _safe_json(
                {
                    "result": "",
                    "error": ("plan_kind must be 'execution' or 'campaign'"),
                }
            )

        normalized_scope_type = (scope_type or "").strip().lower()
        normalized_scope_value = (scope_value or "").strip().lower()
        normalized_campaign_id = (campaign_id or "").strip() or None

        resolved_parent_id = _infer_parent_plan_id(task, parent_id or None)

        # If parent_id points to a campaign, convert to campaign_id
        # instead to prevent a blocking dependency that can never be
        # resolved (campaigns are never completed by executors).
        if resolved_parent_id:
            parent_data = db_read_plan(resolved_parent_id)
            if parent_data is not None:
                if parent_data.get("plan_kind") == "campaign":
                    if not normalized_campaign_id:
                        normalized_campaign_id = resolved_parent_id
                    resolved_parent_id = None

        duplicate = _find_active_duplicate_plan(
            task,
            resolved_parent_id,
            normalized_scope_type,
            normalized_scope_value,
            normalized_plan_kind,
        )
        # Backward-compatible dedupe: also reuse same-family active plans
        # that were created before dependency inference (parent_id None).
        if not duplicate and resolved_parent_id is not None:
            duplicate = _find_active_duplicate_plan(
                task,
                None,
                normalized_scope_type,
                normalized_scope_value,
                normalized_plan_kind,
            )
        if duplicate:
            return _safe_json(
                {
                    "result": _serialize_plan(duplicate),
                    "error": "",
                }
            )

        plan_id = str(uuid.uuid4())
        timestamp = _now()

        plan_steps = []
        for i, step_desc in enumerate(steps, 1):
            plan_steps.append(
                {
                    "id": f"step-{i}",
                    "description": step_desc,
                    "status": "pending",
                    "result": None,
                    "created_at": timestamp,
                    "updated_at": timestamp,
                }
            )

        plan = {
            "id": plan_id,
            "task": task,
            "plan_kind": normalized_plan_kind,
            "status": "pending",
            "parent_id": resolved_parent_id,
            "scope_type": normalized_scope_type,
            "scope_value": normalized_scope_value,
            "campaign_id": normalized_campaign_id,
            "success_conditions": success_conditions,
            "created_at": timestamp,
            "updated_at": timestamp,
            "steps": plan_steps,
            "requeue_count": 0,
            "requeued_at": None,
            "requeue_reason": None,
            "claimed_by": None,
            "claimed_at": None,
        }

        _write_plan(plan)

        response: dict = {"result": _serialize_plan(plan), "error": ""}

        if normalized_plan_kind == "campaign":
            response["warning"] = (
                "Campaign plans are NOT directly executable by the "
                "executor. You MUST create at least one child execution "
                "plan with "
                f'campaign_id="{plan_id}" in this same planning cycle. '
                "A campaign with zero children will be auto-failed by "
                "remediation."
            )

        return _safe_json(response)
    except Exception as exc:
        return _safe_json({"result": "", "error": str(exc)})


def update_plan(
    reason: str,
    plan_id: str,
    step_id: str,
    status: str,
    result: str = "",
    add_steps: list[str] | None = None,
    remove_steps: list[str] | None = None,
    plan_status: str = "",
) -> str:
    """Update a step status and optionally add/remove steps.

    ## When to Use
    Use this tool to mark a step as executing, completed, or failed.
    You can also dynamically add or remove steps from the plan.

    ## Why to Use
    - Track which step is currently executing
    - Record the outcome of a step (success/failure with details)
    - Add new steps discovered during execution
    - Remove steps that are no longer needed

    ## Parameters
    - `reason` (str): Why you're updating this step
    - `plan_id` (str): ID from create_plan response
    - `step_id` (str): ID of the step to update (e.g., "step-1")
    - `status` (str): One of: pending, executing, completed, failed
    - `result` (str): Optional outcome message to store
    - `add_steps` (list[str] | None): Optional steps to append
    - `remove_steps` (list[str] | None): Optional step IDs to remove

    ## Returns
    JSON with:
    - `result`: Updated plan with all steps
    - `error`: Empty on success, or error description
    """
    timestamp = _now()
    valid_statuses = {"pending", "executing", "completed", "failed"}
    valid_plan_statuses = {"pending", "executing", "completed", "failed"}

    try:
        # Read existing plan
        try:
            plan = _read_plan(plan_id)
        except FileNotFoundError:
            return _safe_json(
                {
                    "result": "",
                    "error": (
                        f"Plan '{plan_id}' not found. " f"Use create_plan first."
                    ),
                }
            )

        # Normalize persisted inconsistencies before applying changes.
        normalized = _normalize_plan_for_consistency(plan)
        if normalized:
            _write_plan(plan)

        # Validate status
        if status.lower() not in valid_statuses:
            return _safe_json(
                {
                    "result": "",
                    "error": (
                        f"Invalid status '{status}'. "
                        f"Valid: {', '.join(sorted(valid_statuses))}"
                    ),
                }
            )

        # Prevent mutating terminal plans except idempotent no-op updates.
        plan_is_terminal = plan.get("status") in _TERMINAL_PLAN_STATUSES

        # Find and update the step. Support both canonical step IDs
        # ("step-1") and exact description matches (e.g.
        # "verification-step") for compatibility with agent outputs.
        step_found = False
        changed = False
        target_step = None
        for step in plan["steps"]:
            if step["id"] == step_id:
                target_step = step
                break

        if target_step is None:
            for step in plan["steps"]:
                if step.get("description") == step_id:
                    target_step = step
                    break

        if target_step is not None:
            current_status = target_step.get("status", "pending")
            next_status = status.lower()

            prev_result = target_step.get("result")
            result_changed = bool(result) and result != prev_result

            if plan_is_terminal and (next_status != current_status or result_changed):
                return _safe_json(
                    {
                        "result": _serialize_plan(plan),
                        "error": "",
                        "warning": (
                            "Plan is already terminal. "
                            "No changes applied. "
                            "Do not call update_plan again."
                        ),
                    }
                )

            # Allowed transitions protect against step regressions.
            allowed = {
                "pending": {
                    "pending",
                    "executing",
                    "completed",
                    "failed",
                },
                "executing": {"executing", "completed", "failed"},
                "completed": {"completed"},
                "failed": {"failed"},
            }
            if next_status not in allowed.get(current_status, set()):
                return _safe_json(
                    {
                        "result": "",
                        "error": (
                            "Invalid step status transition "
                            f"{current_status} -> {next_status}"
                        ),
                    }
                )

            target_step["status"] = next_status
            if result:
                target_step["result"] = result
            if next_status != current_status or result_changed:
                target_step["updated_at"] = timestamp
                changed = True
            step_found = True

        if not step_found:
            return _safe_json(
                {
                    "result": "",
                    "error": (f"Step '{step_id}' not found in plan."),
                }
            )

        # Remove steps if requested
        if remove_steps:
            remove_set = set(remove_steps)
            if plan_is_terminal:
                return _safe_json(
                    {
                        "result": _serialize_plan(plan),
                        "error": "",
                        "warning": (
                            "Plan is already terminal. "
                            "No changes applied. "
                            "Do not call update_plan again."
                        ),
                    }
                )
            plan["steps"] = [s for s in plan["steps"] if s["id"] not in remove_set]
            changed = True

        # Add steps if requested
        if add_steps:
            if plan_is_terminal:
                return _safe_json(
                    {
                        "result": _serialize_plan(plan),
                        "error": "",
                        "warning": (
                            "Plan is already terminal. "
                            "No changes applied. "
                            "Do not call update_plan again."
                        ),
                    }
                )
            next_num = len(plan["steps"]) + 1
            for step_desc in add_steps:
                plan["steps"].append(
                    {
                        "id": f"step-{next_num}",
                        "description": step_desc,
                        "status": "pending",
                        "result": None,
                        "created_at": timestamp,
                        "updated_at": timestamp,
                    }
                )
                next_num += 1
            changed = True

        if plan_status:
            if plan_status.lower() not in valid_plan_statuses:
                return _safe_json(
                    {
                        "result": "",
                        "error": (
                            "Invalid plan_status. Valid: "
                            f"{', '.join(sorted(valid_plan_statuses))}"
                        ),
                    }
                )
            requested_status = plan_status.lower()
            if plan.get(
                "status"
            ) in _TERMINAL_PLAN_STATUSES and requested_status != plan.get("status"):
                return _safe_json(
                    {
                        "result": _serialize_plan(plan),
                        "error": "",
                        "warning": (
                            "Plan is already terminal. "
                            "No changes applied. "
                            "Do not call update_plan again."
                        ),
                    }
                )
            if plan.get("status") != requested_status:
                plan["status"] = requested_status
                changed = True

            if requested_status == "executing":
                # Ensure executing plans always have ownership metadata
                # so _is_plan_stale can verify the owner.
                # Preserve existing claimed_by (set by claim_plan) rather
                # than overwriting with a new PID.
                if not plan.get("claimed_by"):
                    plan["claimed_by"] = f"pid:{os.getpid()}"
                    plan["claimed_at"] = timestamp
                    changed = True
                elif plan.get("claimed_at") is None:
                    # Owner exists but claimed_at was cleared — restore
                    plan["claimed_at"] = timestamp
                    changed = True
            else:
                if plan.get("claimed_by") is not None:
                    plan["claimed_by"] = None
                    changed = True
                if plan.get("claimed_at") is not None:
                    plan["claimed_at"] = None
                    changed = True

        derived_status = _derive_plan_status_from_steps(plan)
        if derived_status and plan.get("status") != derived_status:
            plan["status"] = derived_status
            changed = True
            if plan.get("claimed_by") is not None:
                plan["claimed_by"] = None
                changed = True
            if plan.get("claimed_at") is not None:
                plan["claimed_at"] = None
                changed = True

        if changed:
            plan["updated_at"] = timestamp
            _write_plan(plan)

        response: dict = {"result": _serialize_plan(plan), "error": ""}
        if derived_status and derived_status in _TERMINAL_PLAN_STATUSES:
            response["notice"] = (
                f"Plan auto-transitioned to '{derived_status}' "
                "because all steps are terminal. "
                "Do not call update_plan again."
            )
        return _safe_json(response)
    except Exception as exc:
        return _safe_json({"result": "", "error": str(exc)})


def release_plans_for_owner(owner: str) -> dict:
    """Release all plans claimed by a specific owner back to pending.

    Used when a Dramatiq worker fails after claiming a plan,
    so another worker can pick it up.

    Args:
        owner: The owner string (e.g., "executor:dramatiq-<message_id>").

    Returns:
        Dict with released plan IDs and count.
    """
    released = []
    timestamp = _now()

    for plan in db_iter_plans(status="executing"):
        if plan.get("claimed_by") != owner:
            continue

        # Reset plan to pending
        plan["status"] = "pending"
        plan["claimed_by"] = None
        plan["claimed_at"] = None
        plan["updated_at"] = timestamp

        # Reset executing steps back to pending
        for step in plan.get("steps", []):
            if step.get("status") == "executing":
                step["status"] = "pending"
                step["updated_at"] = timestamp

        _write_plan(plan)
        released.append(plan["id"])

    return {"released": released, "count": len(released)}


def recover_stale_plans(reason: str) -> str:
    """Heal inconsistent plans and requeue stale executing plans.

    This is used for autonomous recovery on worker startup.
    """
    try:
        all_plans = db_iter_plans()
        scanned = 0
        normalized = 0
        requeued = 0

        for plan in all_plans:
            scanned += 1

            if _normalize_plan_for_consistency(plan):
                _write_plan(plan)
                normalized += 1

            if _is_plan_stale(plan):
                _requeue_stale_plan(plan)
                requeued += 1

        return _safe_json(
            {
                "result": {
                    "scanned": scanned,
                    "normalized": normalized,
                    "requeued": requeued,
                },
                "error": "",
            }
        )
    except Exception as exc:
        return _safe_json({"result": "", "error": str(exc)})


def claim_plan(reason: str, owner: str | None = None) -> str:
    """Find and claim the oldest eligible pending plan.

    ## When to Use
    Use this tool at the start of an executor cycle to pick up the next
    piece of work. It atomically selects and claims one plan so no other
    executor can grab the same plan.

    ## How It Works
    A plan is eligible when:
    - Its status is ``pending``
    - Its ``plan_kind`` is not ``campaign``
    - It has no ``parent_id``, OR the parent is a campaign (non-blocking),
      OR the parent plan's status is ``completed``

    Stale executing plans (no update for 60 minutes) are automatically
    requeued to pending before claiming.

    The oldest eligible plan (by ``created_at``) is claimed first.

    ## Parameters
    - ``reason`` (str): Why you are claiming a plan
    - ``owner`` (str | None): Optional owner identifier for Dramatiq
      (e.g., ``executor:dramatiq-<message_id>``). If not provided,
      falls back to legacy ``pid:<pid>`` format.

    ## Returns
    JSON with:
    - ``result``: The claimed plan object (status set to ``executing``),
      or ``{"status": "no_eligible_plans", "message": "..."}`` when
      nothing can be claimed
    - ``error``: Empty on success
    """
    try:
        # Phase 1: Heal stale/inconsistent plans (non-atomic).
        for plan in db_iter_plans():
            if _normalize_plan_for_consistency(plan):
                _write_plan(plan)
            if _is_plan_stale(plan):
                _requeue_stale_plan(plan)

        # Phase 2: Atomic claim via BEGIN IMMEDIATE.
        claim_owner = owner or f"pid:{os.getpid()}"
        claimed = db_claim_plan(
            owner=claim_owner,
            timestamp=_now(),
        )

        if claimed is None:
            return _no_eligible_plans_response()

        return _safe_json({"result": _serialize_plan(claimed), "error": ""})
    except Exception as exc:
        return _safe_json({"result": "", "error": str(exc)})


def list_plans(reason: str, status: str = "") -> str:
    """List all plans, optionally filtered by status.

    ## When to Use
    Use this tool to check what plans already exist before creating new
    ones. The planner should call this every cycle to avoid duplicating
    work that is already pending or executing.

    ## Parameters
    - ``reason`` (str): Why you are listing plans
    - ``status`` (str): Optional filter — ``pending``, ``executing``,
      ``completed``, or ``failed``. Omit to list all plans.

    ## Returns
    JSON with:
    - ``result``: List of plan summaries (plan_id, task, status,
      parent_id, total_steps, created_at, updated_at)
    - ``error``: Empty on success
    """
    try:
        status_set: set[str] = set()
        if status:
            status_set = {s.strip().lower() for s in status.split(",") if s.strip()}

        if status_set:
            plans_list = db_iter_plans(status=status_set)
        else:
            plans_list = db_iter_plans()

        plans = []
        for plan in plans_list:
            plans.append(
                {
                    "plan_id": plan["id"],
                    "task": plan["task"],
                    "status": plan["status"],
                    "parent_id": plan.get("parent_id"),
                    "total_steps": len(plan.get("steps", [])),
                    "created_at": plan["created_at"],
                    "updated_at": plan["updated_at"],
                    "stale": _is_plan_stale(plan),
                    "requeue_count": plan.get("requeue_count", 0),
                }
            )

        plans.sort(key=lambda p: p.get("created_at", ""))
        return _safe_json({"result": plans, "error": ""})
    except Exception as exc:
        return _safe_json({"result": "", "error": str(exc)})


def peek_next_plan() -> str | None:
    """Return the task family of the oldest eligible pending plan, or None.

    This is a lightweight read-only function that peeks at plans without
    claiming them. Used by the executor actor to determine which conditional
    skills to load for the executor agent.
    """
    all_plans_list = db_iter_plans()
    all_plans = {p["id"]: p for p in all_plans_list}
    pending = [p for p in all_plans_list if p.get("status") == "pending"]

    pending.sort(key=lambda p: p.get("created_at", ""))
    for plan in pending:
        if plan.get("plan_kind", "execution") == "campaign":
            continue

        parent_id = plan.get("parent_id")
        if parent_id:
            parent = all_plans.get(parent_id)
            if not parent:
                continue  # Orphaned parent — skip
            if (
                parent.get("plan_kind") != "campaign"
                and parent.get("status") != "completed"
            ):
                continue  # Non-campaign parent must be completed
            # Campaign parents: always allow children
        return _task_family(plan.get("task", ""))
    return None
