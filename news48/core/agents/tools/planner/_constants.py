"""Constants and status sets for the planner toolset."""

_STALE_PLAN_TIMEOUT_MINUTES = 60
_MAX_REQUEUE_COUNT = 3

_TERMINAL_STEP_STATUSES = {"completed", "failed"}
_TERMINAL_PLAN_STATUSES = {"completed", "failed"}
_ACTIVE_PLAN_STATUSES = {"pending", "executing"}

_FAMILY_DEPENDENCIES = {
    "download": "fetch",
    "parse": "download",
}

_ARCHIVE_AGE_HOURS = 24
_ARCHIVE_CLEANUP_DAYS = 7
