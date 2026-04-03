"""Persistent planner toolset for agent execution planning.

Provides file-based execution plans with step management capabilities.
Plans are stored as JSON files in the .plans/ directory and survive
process restarts.
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from agents.tools._helpers import _get_function_name, _safe_json

_PLANS_DIR = Path(".plans")


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


def create_plan(reason: str, task: str, steps: list[str]) -> str:
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
    - `task` (str): Overall task description
    - `steps` (list[str]): Ordered list of step descriptions

    ## Returns
    JSON with:
    - `result`: Plan object with id, task, steps, progress
    - `error`: Empty on success
    """
    timestamp = _now()

    try:
        plan_id = str(uuid.uuid4())

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
            "status": "in_progress",
            "created_at": timestamp,
            "updated_at": timestamp,
            "steps": plan_steps,
        }

        _write_plan(plan)

        return _safe_json(
            {
                "result": _serialize_plan(plan),
                "error": "",
                "metadata": {
                    "timestamp": timestamp,
                    "reason": reason,
                    "params": {"task": task, "steps": steps},
                    "operation": _get_function_name(),
                    "plan_id": plan_id,
                    "success": True,
                },
            }
        )
    except Exception as exc:
        return _safe_json(
            {
                "result": "",
                "error": str(exc),
                "metadata": {
                    "timestamp": timestamp,
                    "reason": reason,
                    "params": {"task": task, "steps": steps},
                    "operation": _get_function_name(),
                    "success": False,
                },
            }
        )


def update_plan(
    reason: str,
    plan_id: str,
    step_id: str,
    status: str,
    result: str = "",
    add_steps: list[str] | None = None,
    remove_steps: list[str] | None = None,
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
                    "metadata": {
                        "timestamp": timestamp,
                        "reason": reason,
                        "params": {
                            "plan_id": plan_id,
                            "step_id": step_id,
                        },
                        "operation": _get_function_name(),
                        "success": False,
                    },
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
                    "metadata": {
                        "timestamp": timestamp,
                        "reason": reason,
                        "params": {"step_id": step_id, "status": status},
                        "operation": _get_function_name(),
                        "success": False,
                    },
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
                    "metadata": {
                        "timestamp": timestamp,
                        "reason": reason,
                        "params": {"step_id": step_id, "status": status},
                        "operation": _get_function_name(),
                        "success": False,
                    },
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

        # Update plan status based on steps
        statuses = [s["status"] for s in plan["steps"]]
        if all(s == "completed" for s in statuses):
            plan["status"] = "completed"
        elif any(s == "failed" for s in statuses):
            plan["status"] = "has_failures"
        else:
            plan["status"] = "in_progress"

        plan["updated_at"] = timestamp
        _write_plan(plan)

        return _safe_json(
            {
                "result": _serialize_plan(plan),
                "error": "",
                "metadata": {
                    "timestamp": timestamp,
                    "reason": reason,
                    "params": {
                        "plan_id": plan_id,
                        "step_id": step_id,
                        "status": status,
                        "result": result,
                        "add_steps": add_steps,
                        "remove_steps": remove_steps,
                    },
                    "operation": _get_function_name(),
                    "success": True,
                },
            }
        )
    except Exception as exc:
        return _safe_json(
            {
                "result": "",
                "error": str(exc),
                "metadata": {
                    "timestamp": timestamp,
                    "reason": reason,
                    "params": {
                        "plan_id": plan_id,
                        "step_id": step_id,
                        "status": status,
                    },
                    "operation": _get_function_name(),
                    "success": False,
                },
            }
        )


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
    }
