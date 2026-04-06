"""Persistent planner toolset for agent execution planning.

Provides file-based execution plans with step management capabilities.
Plans are stored as JSON files in the .plans/ directory and survive
process restarts.
"""

import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agents.tools._helpers import _safe_json

_PLANS_DIR = Path(".plans")
_STALE_PLAN_TIMEOUT_MINUTES = 60
_MAX_REQUEUE_COUNT = 3

logger = logging.getLogger(__name__)


_TERMINAL_STEP_STATUSES = {"completed", "failed"}
_TERMINAL_PLAN_STATUSES = {"completed", "failed"}
_ACTIVE_PLAN_STATUSES = {"pending", "executing"}


def _task_family(task: str) -> str:
    """Classify task text into a normalized family key."""
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


def _find_active_duplicate_plan(
    task: str, parent_id: str | None
) -> dict | None:
    """Find an active plan in the same family to prevent duplicates."""
    plans_dir = _ensure_plans_dir()
    family = _task_family(task)
    target_parent = parent_id or None
    candidates = []

    for plan_file in plans_dir.glob("*.json"):
        try:
            plan = json.loads(plan_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        if plan.get("status") not in _ACTIVE_PLAN_STATUSES:
            continue

        if _task_family(plan.get("task", "")) != family:
            continue

        if plan.get("parent_id") != target_parent:
            continue

        candidates.append(plan)

    if not candidates:
        return None

    candidates.sort(key=lambda p: p.get("created_at", ""))
    return candidates[0]


def _derive_plan_status_from_steps(plan: dict) -> str | None:
    """Derive terminal plan status from current step states when possible."""
    steps = plan.get("steps", [])
    if not steps:
        return None

    statuses = {s.get("status") for s in steps}
    if statuses.issubset({"completed"}):
        return "completed"
    if statuses.issubset(_TERMINAL_STEP_STATUSES):
        return "failed"
    return None


def _normalize_plan_for_consistency(plan: dict) -> bool:
    """Normalize plan/step status mismatches.

    Returns:
        True when any field changed, else False.
    """
    changed = False
    timestamp = _now()
    status = plan.get("status")
    steps = plan.get("steps", [])

    # If an executing plan has no claimed_by, it's orphaned — reset to
    # pending so it can be reclaimed by the next executor cycle.
    if status == "executing" and not plan.get("claimed_by"):
        plan["status"] = "pending"
        plan["claimed_by"] = None
        plan["claimed_at"] = None
        status = "pending"
        for step in steps:
            if step.get("status") == "in_progress":
                step["status"] = "pending"
                step["updated_at"] = timestamp
        changed = True

    # If a non-executing plan has in-progress steps,
    # reset those steps to pending.
    if status != "executing":
        for step in steps:
            if step.get("status") == "in_progress":
                step["status"] = "pending"
                step["updated_at"] = timestamp
                changed = True

    # If a plan is terminal, force all in_progress steps to terminal fallback.
    if status in _TERMINAL_PLAN_STATUSES:
        fallback = "failed" if status == "failed" else "completed"
        for step in steps:
            if step.get("status") == "in_progress":
                step["status"] = fallback
                step["updated_at"] = timestamp
                changed = True

    derived = _derive_plan_status_from_steps(plan)
    if derived and status not in _TERMINAL_PLAN_STATUSES:
        plan["status"] = derived
        changed = True

    # If all steps are terminal but the plan terminal status disagrees,
    # prefer the derived status.
    if derived and status in _TERMINAL_PLAN_STATUSES and status != derived:
        plan["status"] = derived
        changed = True

    if changed:
        plan["updated_at"] = timestamp
    return changed


def _parse_claimed_pid(claimed_by: str | None) -> int | None:
    """Parse claimed_by value in format ``pid:<number>``."""
    if not claimed_by or not isinstance(claimed_by, str):
        return None
    if not claimed_by.startswith("pid:"):
        return None
    try:
        return int(claimed_by.split(":", 1)[1])
    except (TypeError, ValueError):
        return None


def _is_pid_alive(pid: int) -> bool:
    """Check process liveness for claim ownership checks."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


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

    Backfills any fields added after the initial schema so that all
    downstream code can rely on their presence.

    Args:
        plan_id: The plan UUID.

    Returns:
        The plan dict.

    Raises:
        FileNotFoundError: If the plan file does not exist.
    """
    path = _plan_path(plan_id)
    with open(path, "r", encoding="utf-8") as f:
        plan = json.load(f)

    # Backfill fields that may be absent in plans created before the
    # claimed_by / requeue_count schema additions.
    plan.setdefault("claimed_by", None)
    plan.setdefault("claimed_at", None)
    plan.setdefault("requeue_count", 0)
    plan.setdefault("requeued_at", None)
    plan.setdefault("requeue_reason", None)

    return plan


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

        duplicate = _find_active_duplicate_plan(task, parent_id or None)
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
            "status": "pending",
            "parent_id": parent_id or None,
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

        # Find and update the step
        step_found = False
        changed = False
        for step in plan["steps"]:
            if step["id"] == step_id:
                current_status = step.get("status", "pending")
                next_status = status.lower()

                prev_result = step.get("result")
                result_changed = bool(result) and result != prev_result

                if plan_is_terminal and (
                    next_status != current_status or result_changed
                ):
                    return _safe_json(
                        {
                            "result": "",
                            "error": (
                                "Plan is already terminal and cannot be "
                                "mutated"
                            ),
                        }
                    )

                # Allowed transitions protect against step regressions.
                allowed = {
                    "pending": {
                        "pending",
                        "in_progress",
                        "completed",
                        "failed",
                    },
                    "in_progress": {"in_progress", "completed", "failed"},
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

                step["status"] = next_status
                if result:
                    step["result"] = result
                if next_status != current_status or result_changed:
                    step["updated_at"] = timestamp
                    changed = True
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
            if plan_is_terminal:
                return _safe_json(
                    {
                        "result": "",
                        "error": (
                            "Plan is already terminal and " "cannot be mutated"
                        ),
                    }
                )
            plan["steps"] = [
                s for s in plan["steps"] if s["id"] not in remove_set
            ]
            changed = True

        # Add steps if requested
        if add_steps:
            if plan_is_terminal:
                return _safe_json(
                    {
                        "result": "",
                        "error": (
                            "Plan is already terminal and " "cannot be mutated"
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
            ) in _TERMINAL_PLAN_STATUSES and requested_status != plan.get(
                "status"
            ):
                return _safe_json(
                    {
                        "result": "",
                        "error": (
                            "Plan is already terminal and "
                            "cannot change status"
                        ),
                    }
                )
            if plan.get("status") != requested_status:
                plan["status"] = requested_status
                changed = True

            if requested_status == "executing":
                # Ensure executing plans always have ownership metadata
                # so _is_plan_stale can verify the owner process.
                if not plan.get("claimed_by"):
                    plan["claimed_by"] = f"pid:{os.getpid()}"
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

    claimed_pid = _parse_claimed_pid(plan.get("claimed_by"))

    # No valid PID claim — ownership is unverifiable, treat as stale so
    # the plan can be requeued and reclaimed by a live executor.
    if claimed_pid is None:
        return True

    # Claimed PID is dead — the executor that owned this plan is gone.
    if not _is_pid_alive(claimed_pid):
        return True

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
    plan["claimed_by"] = None
    plan["claimed_at"] = None

    exceeded_limit = plan["requeue_count"] >= _MAX_REQUEUE_COUNT
    for step in plan.get("steps", []):
        if step.get("status") == "in_progress":
            step["status"] = "failed" if exceeded_limit else "pending"
            step["updated_at"] = timestamp

    if exceeded_limit:
        plan["status"] = "failed"
        plan["requeue_reason"] = (
            f"Plan requeued {plan['requeue_count']} times; "
            "marked failed for automatic remediation"
        )

    _write_plan(plan)
    logger.info(
        "Requeued stale plan %s (requeue_count=%d)",
        plan["id"],
        plan["requeue_count"],
    )


def recover_stale_plans(reason: str) -> str:
    """Heal inconsistent plans and requeue stale executing plans.

    This is used for autonomous recovery on orchestrator startup.
    """
    try:
        plans_dir = _ensure_plans_dir()
        scanned = 0
        normalized = 0
        requeued = 0

        for plan_file in plans_dir.glob("*.json"):
            try:
                plan = json.loads(plan_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue

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

            if _normalize_plan_for_consistency(plan):
                _write_plan(plan)

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
            plan["claimed_by"] = f"pid:{os.getpid()}"
            plan["claimed_at"] = _now()
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
