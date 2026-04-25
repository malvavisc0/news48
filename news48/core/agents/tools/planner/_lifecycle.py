"""Plan lifecycle management: task families, dedup, normalization, staleness."""

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from news48.core import config

from ._constants import (
    _ACTIVE_PLAN_STATUSES,
    _FAMILY_DEPENDENCIES,
    _MAX_REQUEUE_COUNT,
    _STALE_PLAN_TIMEOUT_MINUTES,
    _TERMINAL_PLAN_STATUSES,
    _TERMINAL_STEP_STATUSES,
)
from ._storage import _ensure_plans_dir, _is_valid_uuid, _now, _write_plan

logger = logging.getLogger(__name__)


def _task_family(task: str) -> str:
    """Classify task text into a normalized family key."""
    t = (task or "").strip().lower()
    if "fetch" in t and "feed" in t:
        return "fetch"
    # Parse must be checked before download because parse tasks often include
    # phrases like "downloaded articles".
    if "parse" in t and "article" in t:
        return "parse"
    if "download" in t and "article" in t:
        return "download"
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
    task: str,
    parent_id: str | None,
    scope_type: str = "",
    scope_value: str = "",
    plan_kind: str = "execution",
) -> dict | None:
    """Find an active plan in the same family to prevent duplicates."""
    plans_dir = _ensure_plans_dir()
    family = _task_family(task)
    target_parent = parent_id or None
    target_scope_type = (scope_type or "").strip().lower()
    target_scope_value = (scope_value or "").strip().lower()
    target_plan_kind = (plan_kind or "execution").strip().lower()
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

        if (plan.get("plan_kind") or "execution").strip().lower() != (target_plan_kind):
            continue

        if plan.get("parent_id") != target_parent:
            continue

        if (plan.get("scope_type") or "").strip().lower() != (target_scope_type):
            continue

        if (plan.get("scope_value") or "").strip().lower() != (target_scope_value):
            continue

        candidates.append(plan)

    if not candidates:
        return None

    candidates.sort(key=lambda p: p.get("created_at", ""))
    return candidates[0]


def _find_active_plan_by_family(family: str) -> dict | None:
    """Find the oldest active plan by family, regardless of parent.

    Used to infer pipeline dependencies when callers omit parent_id.
    """
    plans_dir = _ensure_plans_dir()
    candidates = []

    for plan_file in plans_dir.glob("*.json"):
        try:
            plan = json.loads(plan_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        if plan.get("status") not in _ACTIVE_PLAN_STATUSES:
            continue

        if plan.get("plan_kind", "execution") != "execution":
            continue

        if _task_family(plan.get("task", "")) != family:
            continue

        candidates.append(plan)

    if not candidates:
        return None

    candidates.sort(key=lambda p: p.get("created_at", ""))
    return candidates[0]


def _infer_parent_plan_id(task: str, parent_id: str | None) -> str | None:
    """Infer missing parent_id for pipeline plans.

    Enforces canonical pipeline ordering when a caller omits parent_id:
    fetch -> download -> parse.
    """
    if parent_id:
        return parent_id

    family = _task_family(task)
    required_parent_family = _FAMILY_DEPENDENCIES.get(family)
    if not required_parent_family:
        return None

    upstream = _find_active_plan_by_family(required_parent_family)
    if not upstream:
        return None

    return upstream.get("id")


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

    Also detects and repairs campaign-parent deadlocks: if a non-terminal
    plan's ``parent_id`` points to a campaign, the blocking dependency is
    converted to a non-blocking ``campaign_id`` grouping field.  Orphaned
    non-UUID ``parent_id`` references are also cleared.

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
            if step.get("status") == "executing":
                step["status"] = "pending"
                step["updated_at"] = timestamp
        changed = True

    # If a non-executing plan has executing steps,
    # reset those steps to pending.
    if status != "executing":
        for step in steps:
            if step.get("status") == "executing":
                step["status"] = "pending"
                step["updated_at"] = timestamp
                changed = True

    # If a plan is terminal, force all executing steps to terminal fallback.
    if status in _TERMINAL_PLAN_STATUSES:
        fallback = "failed" if status == "failed" else "completed"
        for step in steps:
            if step.get("status") == "executing":
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

    # If parent_id points to a campaign, convert to campaign_id.
    # Campaigns are never completed by executors, so children with
    # parent_id pointing at a campaign would be permanently blocked.
    parent_id = plan.get("parent_id")
    if parent_id and status not in _TERMINAL_PLAN_STATUSES:
        parent_file = config.PLANS_DIR / f"{parent_id}.json"
        if parent_file.exists():
            try:
                parent = json.loads(parent_file.read_text(encoding="utf-8"))
                if parent.get("plan_kind") == "campaign":
                    plan["parent_id"] = None
                    if not plan.get("campaign_id"):
                        plan["campaign_id"] = parent_id
                    changed = True
            except (json.JSONDecodeError, OSError):
                pass
        elif not _is_valid_uuid(parent_id):
            # Orphaned non-UUID parent_id
            plan["parent_id"] = None
            changed = True

    if changed:
        plan["updated_at"] = timestamp
    return changed


def _is_pid_alive(pid: int) -> bool:
    """Check if a process with the given PID is still running.

    On Linux, treats zombie processes as not alive for orchestration
    purposes so stale PIDs do not block scheduling or shutdown logic.
    """
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)  # Signal 0 = check existence
    except (ProcessLookupError, PermissionError):
        return False

    stat_path = f"/proc/{pid}/stat"
    try:
        stat = open(stat_path, "r", encoding="utf-8").read()
    except OSError:
        return True

    try:
        _pid, remainder = stat.split("(", 1)
        _comm, remainder = remainder.rsplit(")", 1)
        parts = remainder.strip().split()
        state = parts[0]
    except (IndexError, ValueError):
        return True

    return state != "Z"


def _parse_claimed_pid(claimed_by: str | None) -> int | None:
    """Parse claimed_by value in format ``pid:<number>``.

    Returns None for non-PID formats like ``executor:dramatiq-<id>``.
    """
    if not claimed_by or not isinstance(claimed_by, str):
        return None
    if not claimed_by.startswith("pid:"):
        return None
    try:
        return int(claimed_by.split(":", 1)[1])
    except (TypeError, ValueError):
        return None


def _is_plan_stale(plan: dict) -> bool:
    """Check if an executing plan is stale (timed out).

    Handles both legacy PID-based ownership (``pid:<number>``) and
    modern Dramatiq message-based ownership
    (``executor:dramatiq-<message_id>``).

    Args:
        plan: The plan dict.

    Returns:
        True if the plan is executing and its updated_at is older
        than the stale timeout threshold.
    """
    if plan.get("status") != "executing":
        return False

    claimed_by = plan.get("claimed_by")
    claimed_pid = _parse_claimed_pid(claimed_by)

    if claimed_pid is not None:
        # Legacy PID-based ownership: check if the process is alive
        if not _is_pid_alive(claimed_pid):
            # PID is dead — the executor that owned this plan is gone
            return True
    elif claimed_by and claimed_by.startswith("executor:dramatiq-"):
        # Modern Dramatiq ownership: no PID to check, rely on timeout
        pass
    elif claimed_by is None:
        # No ownership metadata — treat as stale so it can be requeued
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

    Reverts all executing steps to pending, increments requeue_count,
    and sets requeued_at and requeue_reason.

    Args:
        plan: The plan dict to requeue.
    """
    timestamp = _now()
    plan["status"] = "pending"
    plan["requeue_count"] = plan.get("requeue_count", 0) + 1
    plan["requeued_at"] = timestamp
    plan["requeue_reason"] = (
        f"Plan was stale: no update for " f"{_STALE_PLAN_TIMEOUT_MINUTES} minutes"
    )
    plan["updated_at"] = timestamp
    plan["claimed_by"] = None
    plan["claimed_at"] = None

    exceeded_limit = plan["requeue_count"] >= _MAX_REQUEUE_COUNT
    for step in plan.get("steps", []):
        if step.get("status") == "executing":
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


def _auto_complete_campaigns(plans_dir: Path | None = None) -> int:
    """Mark campaigns as completed when all children are terminal.

    Checks both ``campaign_id`` and ``parent_id`` links to find children.
    A campaign whose every child is ``completed`` gets status
    ``completed``; if any child is ``failed`` the campaign is marked
    ``failed``.  Campaigns with no children at all are left unchanged
    (handled by remediation's orphaned-campaign check).

    Returns the number of campaigns auto-completed.
    """
    plans_dir = plans_dir or _ensure_plans_dir()
    all_plans: dict[str, dict] = {}
    for plan_file in plans_dir.glob("*.json"):
        try:
            plan = json.loads(plan_file.read_text(encoding="utf-8"))
            all_plans[plan["id"]] = plan
        except (json.JSONDecodeError, OSError):
            continue

    completed = 0
    for plan_id, plan in all_plans.items():
        if plan.get("plan_kind") != "campaign":
            continue
        if plan.get("status") != "pending":
            continue

        children = [
            p
            for p in all_plans.values()
            if p.get("id") != plan_id
            and (p.get("campaign_id") == plan_id or p.get("parent_id") == plan_id)
        ]
        if not children:
            continue

        if all(c.get("status") in _TERMINAL_PLAN_STATUSES for c in children):
            all_completed = all(c.get("status") == "completed" for c in children)
            plan["status"] = "completed" if all_completed else "failed"
            plan["updated_at"] = _now()
            _write_plan(plan)
            completed += 1

    return completed
