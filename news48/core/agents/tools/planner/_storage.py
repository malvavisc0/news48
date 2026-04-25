"""Plan file I/O: directory management, read/write, serialization, archiving."""

import json
import logging
import os
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from news48.core import config

from .._helpers import _safe_json
from ._constants import (
    _ARCHIVE_AGE_HOURS,
    _ARCHIVE_CLEANUP_DAYS,
    _TERMINAL_PLAN_STATUSES,
)

logger = logging.getLogger(__name__)


def _ensure_plans_dir() -> Path:
    """Ensure the data/plans directory exists.

    Returns:
        Path to the data/plans directory.
    """
    config.PLANS_DIR.mkdir(parents=True, exist_ok=True)
    return config.PLANS_DIR


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
    plan.setdefault("plan_kind", "execution")
    plan.setdefault("scope_type", "")
    plan.setdefault("scope_value", "")
    plan.setdefault("campaign_id", None)

    return plan


def _write_plan(plan: dict) -> None:
    """Write a plan to disk atomically.

    Uses write-to-temp-then-rename so a crash mid-write cannot
    corrupt the plan JSON file.

    Args:
        plan: The plan dict to write.
    """
    path = _plan_path(plan["id"])
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(plan, f, indent=2, default=str)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        # Clean up temp file on any failure
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


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
    """Move terminal plans older than 24 hours to the archive directory.

    This keeps ``claim_plan()`` and ``list_plans()`` scans fast by
    removing old completed/failed plans from the main directory.

    Returns:
        Dict with ``archived`` count and ``errors`` count.
    """
    plans_dir = _ensure_plans_dir()
    (config.PLANS_DIR / "archive").mkdir(exist_ok=True)

    cutoff = (
        datetime.now(timezone.utc) - timedelta(hours=_ARCHIVE_AGE_HOURS)
    ).isoformat()

    archived = 0
    errors = 0

    for plan_file in plans_dir.glob("*.json"):
        try:
            plan = json.loads(plan_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        if plan.get("status") not in _TERMINAL_PLAN_STATUSES:
            continue

        updated_at = plan.get("updated_at", "")
        if not updated_at or updated_at > cutoff:
            continue

        # Move to archive
        dest = config.PLANS_DIR / "archive" / plan_file.name
        try:
            plan_file.replace(dest)
            archived += 1
        except OSError as exc:
            logger.warning("Failed to archive plan %s: %s", plan_file.name, exc)
            errors += 1

    return {"archived": archived, "errors": errors}


def _archive_cleanup() -> dict:
    """Delete archived plans older than 7 days."""
    archive_dir = config.PLANS_DIR / "archive"
    if not archive_dir.exists():
        return {"cleaned": 0, "errors": 0}

    cutoff = (
        datetime.now(timezone.utc) - timedelta(days=_ARCHIVE_CLEANUP_DAYS)
    ).isoformat()

    cleaned = 0
    errors = 0
    for plan_file in archive_dir.glob("*.json"):
        try:
            plan = json.loads(plan_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # Corrupt file — just delete it
            try:
                plan_file.unlink()
                cleaned += 1
            except OSError:
                errors += 1
            continue

        updated_at = plan.get("updated_at", "")
        if not updated_at or updated_at <= cutoff:
            try:
                plan_file.unlink()
                cleaned += 1
            except OSError as exc:
                logger.warning(
                    "Failed to delete archived plan %s: %s",
                    plan_file.name,
                    exc,
                )
                errors += 1

    return {"cleaned": cleaned, "errors": errors}
