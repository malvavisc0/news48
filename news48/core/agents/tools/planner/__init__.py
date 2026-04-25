"""Persistent planner toolset for agent execution planning.

Provides file-based execution plans with step management capabilities.
Plans are stored as JSON files in the data/plans/ directory and survive
process restarts.

This package splits the original monolithic planner.py into focused
sub-modules while preserving all public import paths for backward
compatibility.
"""

from ._constants import (
    _ACTIVE_PLAN_STATUSES,
    _ARCHIVE_AGE_HOURS,
    _ARCHIVE_CLEANUP_DAYS,
    _FAMILY_DEPENDENCIES,
    _MAX_REQUEUE_COUNT,
    _STALE_PLAN_TIMEOUT_MINUTES,
    _TERMINAL_PLAN_STATUSES,
    _TERMINAL_STEP_STATUSES,
)
from ._lifecycle import (
    _auto_complete_campaigns,
    _derive_plan_status_from_steps,
    _find_active_duplicate_plan,
    _find_active_plan_by_family,
    _infer_parent_plan_id,
    _is_pid_alive,
    _is_plan_stale,
    _normalize_plan_for_consistency,
    _parse_claimed_pid,
    _requeue_stale_plan,
    _task_family,
)
from ._storage import (
    _archive_cleanup,
    _ensure_plans_dir,
    _is_valid_uuid,
    _no_eligible_plans_response,
    _now,
    _plan_path,
    _read_plan,
    _serialize_plan,
    _write_plan,
    archive_terminal_plans,
)
from ._tools import (
    claim_plan,
    create_plan,
    list_plans,
    peek_next_plan,
    recover_stale_plans,
    release_plans_for_owner,
    update_plan,
)

__all__ = [
    "archive_terminal_plans",
    "claim_plan",
    "create_plan",
    "list_plans",
    "peek_next_plan",
    "recover_stale_plans",
    "release_plans_for_owner",
    "update_plan",
]
