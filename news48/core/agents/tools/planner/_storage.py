"""Plan storage helpers: serialization, archiving, and DB delegation."""

import logging
import uuid
from datetime import datetime, timedelta, timezone

from .._helpers import _safe_json
from ._constants import _ARCHIVE_AGE_HOURS, _ARCHIVE_CLEANUP_DAYS
from ._db import (
    db_archive_cleanup,
    db_archive_terminal_plans,
    db_read_plan,
    db_write_plan,
)

logger = logging.getLogger(__name__)


def _read_plan(plan_id: str) -> dict:
    """Read a plan from the database.

    Backfills any fields added after the initial schema so that all
    downstream code can rely on their presence.

    Args:
        plan_id: The plan UUID.

    Returns:
        The plan dict.

    Raises:
        FileNotFoundError: If the plan does not exist.
    """
    plan = db_read_plan(plan_id)
    if plan is None:
        raise FileNotFoundError(f"Plan {plan_id} not found")
    return plan


def _write_plan(plan: dict) -> None:
    """Write a plan to the database.

    Args:
        plan: The plan dict to write.
    """
    db_write_plan(plan)


def _now() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _is_valid_uuid(value: str) -> bool:
    """Check whether a string looks like a UUID (8-4-4-4-12 hex format)."""
    if not value:
        return False
    try:
        uuid.UUID(value)
        return True
    except (ValueError, AttributeError):
        return False


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
    executing = sum(1 for s in steps if s["status"] == "executing")
    pending = sum(1 for s in steps if s["status"] == "pending")

    return {
        "plan_id": plan["id"],
        "task": plan["task"],
        "plan_kind": plan.get("plan_kind", "execution"),
        "status": plan["status"],
        "parent_id": plan.get("parent_id"),
        "scope_type": plan.get("scope_type", ""),
        "scope_value": plan.get("scope_value", ""),
        "campaign_id": plan.get("campaign_id"),
        "success_conditions": plan.get("success_conditions", []),
        "steps": steps,
        "total_steps": len(steps),
        "progress": {
            "total": len(steps),
            "completed": completed,
            "failed": failed,
            "executing": executing,
            "pending": pending,
        },
        "created_at": plan["created_at"],
        "updated_at": plan["updated_at"],
        "requeue_count": plan.get("requeue_count", 0),
        "requeued_at": plan.get("requeued_at"),
        "requeue_reason": plan.get("requeue_reason"),
    }


def _no_eligible_plans_response() -> str:
    """Return the canonical JSON response for no eligible plans."""
    return _safe_json(
        {
            "result": {
                "status": "no_eligible_plans",
                "message": (
                    "No eligible pending plans found. "
                    "Stop now. Do not call any more tools."
                ),
            },
            "error": "",
        }
    )


def archive_terminal_plans() -> dict:
    """Delete terminal plans older than 24 hours.

    This keeps ``claim_plan()`` and ``list_plans()`` fast by
    removing old completed/failed plans from the database.

    Returns:
        Dict with ``archived`` count and ``errors`` count.
    """
    cutoff = (
        datetime.now(timezone.utc) - timedelta(hours=_ARCHIVE_AGE_HOURS)
    ).isoformat()

    try:
        archived = db_archive_terminal_plans(cutoff)
        return {"archived": archived, "errors": 0}
    except Exception as exc:
        logger.warning("Failed to archive terminal plans: %s", exc)
        return {"archived": 0, "errors": 1}


def _archive_cleanup() -> dict:
    """Delete archived plans older than 7 days."""
    cutoff = (
        datetime.now(timezone.utc) - timedelta(days=_ARCHIVE_CLEANUP_DAYS)
    ).isoformat()

    try:
        cleaned = db_archive_cleanup(cutoff)
        return {"cleaned": cleaned, "errors": 0}
    except Exception as exc:
        logger.warning("Failed to clean up archived plans: %s", exc)
        return {"cleaned": 0, "errors": 1}
