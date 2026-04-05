"""Persistent planner toolset for agent execution planning.

Provides file-based execution plans with step management capabilities.
Plans are stored as JSON files in the .plans/ directory and survive
process restarts.
"""

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agents.tools._helpers import _safe_json

_PLANS_DIR = Path(".plans")
_STALE_PLAN_TIMEOUT_MINUTES = 60

logger = logging.getLogger(__name__)


def _ensure_plans_dir() -> Path:
    """Ensure the .plans directory exists.

    Returns:
        Path to the .plans directory.
    """
    _PLANS_DIR.mkdir(exist_ok=True)
    return _PLANS_DIR


def _plan_path(plan_id: str) -> Path:
    """Get the file path for a plan.

    Args:
        plan_id: The plan UUID.

    Returns:
        Path to the plan JSON file.
    """
    return _ensure_plans_dir() / f"{plan_id}.json"


def _read_plan(plan_id: str) -> dict:
    """Read a plan from disk.

    Args:
        plan_id: The plan UUID.

    Returns:
        The plan dict.

    Raises:
        FileNotFoundError: If the plan file does not exist.
    """
    path = _plan_path(plan_id)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_plan(plan: dict) -> None:
    """Write a plan to disk.

    Args:
        plan: The plan dict to write.
    """
    path = _plan_path(plan["id"])
    with open(path, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2, default=str)


def _now() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def create_plan(
    reason: str,
    task: str,
    steps: list[str],
    success_conditions: list[str],
    parent_id: str = "",
) -> str:
    """Create a new execution plan, persist to .plans/{id}.json.

    ## When to Use
    Use this tool when you need to break down a complex task into ordered
    steps that can be tracked and managed. Required before using
    `update_plan`.

    ## Why to Use
    - Track progress through multi-step workflows
    - Maintain state across agent interactions and restarts
    - Record results for each step individually
    - Plans are persisted to disk and survive process exits

    ## Parameters
    - `reason` (str): Why planning is needed for this task
    - `task` (str): Overall task description (required, non-empty)
    - `steps` (list[str]): Ordered list of step descriptions
    - `success_conditions` (list[str]): Non-empty list of verifiable outcome
      statements. Each condition must describe an outcome (not an action)
      that can be verified using CLI commands like `news48 ... --json`.
    - `parent_id` (str): Optional parent plan ID for sequencing

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
            return _safe_json(
                {"result": "", "error": "success_conditions is required"}
            )

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
                        "error": f"success_conditions[{i}] cannot be blank",
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
            "status": "pending",
            "parent_id": parent_id or None,
            "success_conditions": success_conditions,
            "created_at": timestamp,
            "updated_at": timestamp,
            "steps": plan_steps,
            "requeue_count": 0,
            "requeued_at": None,
            "requeue_reason": None,
        }

        _write_plan(plan)

        return _safe_json({"result": _serialize_plan(plan), "error": ""})
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
    Use this tool to mark a step as in_progress, completed, or failed.
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
    - `status` (str): One of: pending, in_progress, completed, failed
    - `result` (str): Optional outcome message to store
    - `add_steps` (list[str] | None): Optional steps to append
    - `remove_steps` (list[str] | None): Optional step IDs to remove

    ## Returns
    JSON with:
    - `result`: Updated plan with all steps
    - `error`: Empty on success, or error description
    """
    timestamp = _now()
    valid_statuses = {"pending", "in_progress", "completed", "failed"}
    valid_plan_statuses = {"pending", "executing", "completed", "failed"}

    try:
        # Read existing plan
        try:
            plan = _read_plan(plan_id)
        except FileNotFoundError:
            return _safe_json(
                {
                    "result": "",
                    "error": f"Plan '{plan_id}' not found. "
                    f"Use create_plan first.",
                }
            )

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

        # Find and update the step
        step_found = False
        for step in plan["steps"]:
            if step["id"] == step_id:
                step["status"] = status.lower()
                if result:
                    step["result"] = result
                step["updated_at"] = timestamp
                step_found = True
                break

        if not step_found:
            return _safe_json(
                {
                    "result": "",
                    "error": f"Step '{step_id}' not found in plan.",
                }
            )

        # Remove steps if requested
        if remove_steps:
            remove_set = set(remove_steps)
            plan["steps"] = [
                s for s in plan["steps"] if s["id"] not in remove_set
            ]

        # Add steps if requested
        if add_steps:
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
            plan["status"] = plan_status.lower()

        plan["updated_at"] = timestamp
        _write_plan(plan)

        return _safe_json({"result": _serialize_plan(plan), "error": ""})
    except Exception as exc:
        return _safe_json({"result": "", "error": str(exc)})


def _serialize_plan(plan: dict) -> dict:
    """Serialize a plan dict for tool responses.

    Args:
        plan: The plan dict.

    Returns:
        A serialized plan dict with progress summary.
    """
    steps = plan.get("steps", [])
    completed = sum(1 for s in steps if s["status"] == "completed")
    failed = sum(1 for s in steps if s["status"] == "failed")
    in_progress = sum(1 for s in steps if s["status"] == "in_progress")
    pending = sum(1 for s in steps if s["status"] == "pending")

    return {
        "plan_id": plan["id"],
        "task": plan["task"],
        "status": plan["status"],
        "parent_id": plan.get("parent_id"),
        "success_conditions": plan.get("success_conditions", []),
        "steps": steps,
        "total_steps": len(steps),
        "progress": {
            "total": len(steps),
            "completed": completed,
            "failed": failed,
            "in_progress": in_progress,
            "pending": pending,
        },
        "created_at": plan["created_at"],
        "updated_at": plan["updated_at"],
        "requeue_count": plan.get("requeue_count", 0),
        "requeued_at": plan.get("requeued_at"),
        "requeue_reason": plan.get("requeue_reason"),
    }


def _is_plan_stale(plan: dict) -> bool:
    """Check if an executing plan is stale (timed out).

    Args:
        plan: The plan dict.

    Returns:
        True if the plan is executing and its updated_at is older
        than the stale timeout threshold.
    """
    if plan.get("status") != "executing":
        return False
    updated_at = plan.get("updated_at", "")
    if not updated_at:
        return True
    try:
        updated = datetime.fromisoformat(updated_at)
        threshold = timedelta(minutes=_STALE_PLAN_TIMEOUT_MINUTES)
        return datetime.now(timezone.utc) - updated > threshold
    except (ValueError, TypeError):
        return True


def _requeue_stale_plan(plan: dict) -> None:
    """Reset a stale executing plan back to pending.

    Reverts all in_progress steps to pending, increments requeue_count,
    and sets requeued_at and requeue_reason.

    Args:
        plan: The plan dict to requeue.
    """
    timestamp = _now()
    plan["status"] = "pending"
    plan["requeue_count"] = plan.get("requeue_count", 0) + 1
    plan["requeued_at"] = timestamp
    plan["requeue_reason"] = (
        f"Plan was stale: no update for "
        f"{_STALE_PLAN_TIMEOUT_MINUTES} minutes"
    )
    plan["updated_at"] = timestamp
    for step in plan.get("steps", []):
        if step.get("status") == "in_progress":
            step["status"] = "pending"
            step["updated_at"] = timestamp
    _write_plan(plan)
    logger.info(
        "Requeued stale plan %s (requeue_count=%d)",
        plan["id"],
        plan["requeue_count"],
    )


def claim_plan(reason: str) -> str:
    """Find and claim the oldest eligible pending plan.

    ## When to Use
    Use this tool at the start of an executor cycle to pick up the next
    piece of work. It atomically selects and claims one plan so no other
    executor can grab the same plan.

    ## How It Works
    A plan is eligible when:
    - Its status is ``pending``
    - It has no ``parent_id``, OR the parent plan's status is ``completed``

    Stale executing plans (no update for 60 minutes) are automatically
    requeued to pending before claiming.

    The oldest eligible plan (by ``created_at``) is claimed first.

    ## Parameters
    - ``reason`` (str): Why you are claiming a plan

    ## Returns
    JSON with:
    - ``result``: The claimed plan object (status set to ``executing``),
      or empty string if no eligible plans exist
    - ``error``: Empty on success
    """
    try:
        plans_dir = _ensure_plans_dir()
        all_plans = {}
        pending_plans = []

        for plan_file in plans_dir.glob("*.json"):
            try:
                plan = json.loads(plan_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue

            all_plans[plan["id"]] = plan

            # Requeue stale executing plans
            if _is_plan_stale(plan):
                _requeue_stale_plan(plan)

            if plan.get("status") == "pending":
                pending_plans.append(plan)

        if not pending_plans:
            return _safe_json({"result": "", "error": ""})

        pending_plans.sort(key=lambda p: p.get("created_at", ""))

        for plan in pending_plans:
            parent_id = plan.get("parent_id")
            if parent_id:
                parent = all_plans.get(parent_id)
                if not parent or parent.get("status") != "completed":
                    continue

            plan["status"] = "executing"
            plan["updated_at"] = _now()
            _write_plan(plan)
            return _safe_json({"result": _serialize_plan(plan), "error": ""})

        return _safe_json({"result": "", "error": ""})
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
        plans_dir = _ensure_plans_dir()
        plans = []

        for plan_file in plans_dir.glob("*.json"):
            try:
                plan = json.loads(plan_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue

            if status and plan.get("status") != status.lower():
                continue

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
