"""SQLite storage backend for the planner toolset."""

import json
import sqlite3

from news48.core import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS plans (
    id                TEXT PRIMARY KEY,
    task              TEXT NOT NULL,
    plan_kind         TEXT NOT NULL DEFAULT 'execution',
    status            TEXT NOT NULL DEFAULT 'pending',
    parent_id         TEXT,
    scope_type        TEXT NOT NULL DEFAULT '',
    scope_value       TEXT NOT NULL DEFAULT '',
    campaign_id       TEXT,
    success_conditions TEXT NOT NULL DEFAULT '[]',
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    requeue_count     INTEGER NOT NULL DEFAULT 0,
    requeued_at       TEXT,
    requeue_reason    TEXT,
    claimed_by        TEXT,
    claimed_at        TEXT
);

CREATE INDEX IF NOT EXISTS idx_plans_status ON plans(status);
CREATE INDEX IF NOT EXISTS idx_plans_parent_id ON plans(parent_id);
CREATE INDEX IF NOT EXISTS idx_plans_campaign_id ON plans(campaign_id);
CREATE INDEX IF NOT EXISTS idx_plans_claimed_by ON plans(claimed_by);
CREATE INDEX IF NOT EXISTS idx_plans_created_at ON plans(created_at);

CREATE TABLE IF NOT EXISTS plan_steps (
    plan_id     TEXT NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
    step_id     TEXT NOT NULL,
    description TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',
    result      TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (plan_id, step_id)
);

CREATE INDEX IF NOT EXISTS idx_plan_steps_plan_id
    ON plan_steps(plan_id);
"""

# Module-level connection cache (one per process).
_conn: sqlite3.Connection | None = None


def _close_conn() -> None:
    """Close the cached connection and reset the cache.

    Called by test fixtures to ensure temp DB files are not held open.
    """
    global _conn
    if _conn is not None:
        try:
            _conn.close()
        except Exception:
            pass
        _conn = None


def _get_conn() -> sqlite3.Connection:
    """Return a SQLite connection to plans.db.

    WAL mode, auto-create tables, foreign keys enabled.
    """
    global _conn
    if _conn is not None:
        return _conn

    db_path = config.PLANS_DB
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=10, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    _conn = conn
    return conn


def _row_to_plan(row: sqlite3.Row, conn: sqlite3.Connection) -> dict:
    """Convert a plan Row + its steps into the canonical plan dict."""
    plan = dict(row)
    plan["success_conditions"] = json.loads(plan.get("success_conditions") or "[]")
    step_rows = conn.execute(
        "SELECT step_id, description, status, result, "
        "created_at, updated_at "
        "FROM plan_steps WHERE plan_id = ? ORDER BY step_id",
        (plan["id"],),
    ).fetchall()
    plan["steps"] = [
        {
            "id": r["step_id"],
            "description": r["description"],
            "status": r["status"],
            "result": r["result"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }
        for r in step_rows
    ]
    return plan


def db_read_plan(plan_id: str) -> dict | None:
    """Read a plan by ID. Returns None if not found."""
    conn = _get_conn()
    row = conn.execute("SELECT * FROM plans WHERE id = ?", (plan_id,)).fetchone()
    if row is None:
        return None
    return _row_to_plan(row, conn)


def db_write_plan(plan: dict) -> None:
    """Insert or update a plan and its steps.

    Uses INSERT OR REPLACE for the plan and replaces all steps.
    """
    conn = _get_conn()
    plan_id = plan["id"]
    conn.execute(
        "INSERT OR REPLACE INTO plans ("
        "  id, task, plan_kind, status, parent_id, "
        "  scope_type, scope_value, campaign_id, "
        "  success_conditions, created_at, updated_at, "
        "  requeue_count, requeued_at, requeue_reason, "
        "  claimed_by, claimed_at"
        ") VALUES ("
        "  ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?"
        ")",
        (
            plan_id,
            plan["task"],
            plan.get("plan_kind", "execution"),
            plan["status"],
            plan.get("parent_id"),
            plan.get("scope_type", ""),
            plan.get("scope_value", ""),
            plan.get("campaign_id"),
            json.dumps(plan.get("success_conditions", [])),
            plan["created_at"],
            plan["updated_at"],
            plan.get("requeue_count", 0),
            plan.get("requeued_at"),
            plan.get("requeue_reason"),
            plan.get("claimed_by"),
            plan.get("claimed_at"),
        ),
    )
    # Replace all steps
    conn.execute("DELETE FROM plan_steps WHERE plan_id = ?", (plan_id,))
    for step in plan.get("steps", []):
        conn.execute(
            "INSERT INTO plan_steps ("
            "  plan_id, step_id, description, status, "
            "  result, created_at, updated_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                plan_id,
                step["id"],
                step["description"],
                step["status"],
                step.get("result"),
                step["created_at"],
                step["updated_at"],
            ),
        )
    conn.commit()


def db_iter_plans(status: str | set[str] | None = None) -> list[dict]:
    """Iterate all plans, optionally filtered by status.

    Returns a list of plan dicts (same shape as JSON-based code).
    """
    conn = _get_conn()
    if status is None:
        rows = conn.execute("SELECT * FROM plans ORDER BY created_at").fetchall()
    elif isinstance(status, str):
        rows = conn.execute(
            "SELECT * FROM plans WHERE status = ? ORDER BY created_at",
            (status,),
        ).fetchall()
    else:
        # status is a set
        placeholders = ",".join("?" for _ in status)
        rows = conn.execute(
            f"SELECT * FROM plans WHERE status IN "
            f"({placeholders}) ORDER BY created_at",
            tuple(status),
        ).fetchall()
    return [_row_to_plan(r, conn) for r in rows]


def db_delete_plan(plan_id: str) -> None:
    """Delete a plan (cascades to steps via FK)."""
    conn = _get_conn()
    conn.execute("DELETE FROM plans WHERE id = ?", (plan_id,))
    conn.commit()


def db_update_plan_fields(plan_id: str, **fields) -> None:
    """Update specific fields on a plan row."""
    if not fields:
        return
    conn = _get_conn()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [plan_id]
    conn.execute(
        f"UPDATE plans SET {set_clause} WHERE id = ?",
        values,
    )
    conn.commit()


def db_update_step(
    plan_id: str,
    step_id: str,
    status: str | None = None,
    result: str | None = None,
    updated_at: str | None = None,
) -> None:
    """Update a single step's fields."""
    conn = _get_conn()
    sets = []
    vals = []
    if status is not None:
        sets.append("status = ?")
        vals.append(status)
    if result is not None:
        sets.append("result = ?")
        vals.append(result)
    if updated_at is not None:
        sets.append("updated_at = ?")
        vals.append(updated_at)
    if not sets:
        return
    vals.extend([plan_id, step_id])
    conn.execute(
        f"UPDATE plan_steps SET {', '.join(sets)} " "WHERE plan_id = ? AND step_id = ?",
        vals,
    )
    conn.commit()


def db_insert_step(
    plan_id: str,
    step_id: str,
    description: str,
    status: str = "pending",
    result: str | None = None,
    created_at: str = "",
    updated_at: str = "",
) -> None:
    """Insert a new step into a plan."""
    conn = _get_conn()
    conn.execute(
        "INSERT INTO plan_steps "
        "(plan_id, step_id, description, status, result, "
        "created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            plan_id,
            step_id,
            description,
            status,
            result,
            created_at,
            updated_at,
        ),
    )
    conn.commit()


def db_delete_steps(plan_id: str, step_ids: list[str]) -> None:
    """Delete specific steps from a plan."""
    if not step_ids:
        return
    conn = _get_conn()
    placeholders = ",".join("?" for _ in step_ids)
    conn.execute(
        f"DELETE FROM plan_steps WHERE plan_id = ? " f"AND step_id IN ({placeholders})",
        [plan_id] + step_ids,
    )
    conn.commit()


def db_claim_plan(
    owner: str,
    timestamp: str,
    parent_statuses: dict[str, str] | None = None,
) -> dict | None:
    """Atomically claim the oldest eligible pending plan.

    Uses ``BEGIN IMMEDIATE`` to serialize concurrent claim attempts.
    A plan is eligible when:
    - ``status = 'pending'``
    - ``plan_kind != 'campaign'``
    - ``parent_id IS NULL``, OR the parent is a campaign
      (non-blocking), OR the parent is completed.

    Args:
        owner: The claimant identifier (e.g. ``pid:1234`` or
            ``executor:dramatiq-<id>``).
        timestamp: ISO 8601 timestamp for ``claimed_at`` /
            ``updated_at``.
        parent_statuses: Optional pre-fetched ``{id: status}`` map.
            If provided, the function skips a ``SELECT`` for parent
            lookups.  Falls back to a sub-query when *None*.

    Returns:
        The claimed plan dict (with steps), or *None* when no
        eligible plan exists.
    """
    conn = _get_conn()

    # BEGIN IMMEDIATE blocks other writers until COMMIT.
    conn.execute("BEGIN IMMEDIATE")
    try:
        # Find the oldest eligible pending plan.
        row = conn.execute(
            "SELECT p.id FROM plans p "
            "WHERE p.status = 'pending' "
            "AND p.plan_kind != 'campaign' "
            "AND ("
            "  p.parent_id IS NULL "
            "  OR EXISTS ("
            "    SELECT 1 FROM plans pp"
            "    WHERE pp.id = p.parent_id"
            "    AND pp.plan_kind = 'campaign'"
            "  )"
            "  OR EXISTS ("
            "    SELECT 1 FROM plans pp"
            "    WHERE pp.id = p.parent_id"
            "    AND pp.plan_kind != 'campaign'"
            "    AND pp.status = 'completed'"
            "  )"
            ") "
            "ORDER BY p.created_at ASC "
            "LIMIT 1",
        ).fetchone()

        if row is None:
            conn.execute("ROLLBACK")
            return None

        plan_id = row["id"]
        conn.execute(
            "UPDATE plans SET status = 'executing', "
            "claimed_by = ?, claimed_at = ?, updated_at = ? "
            "WHERE id = ?",
            (owner, timestamp, timestamp, plan_id),
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise

    # Re-read the full plan (with steps) outside the transaction.
    return db_read_plan(plan_id)


def db_archive_terminal_plans(cutoff: str) -> int:
    """Soft-archive: move terminal plans older than *cutoff* to
    ``status='archived'``.

    Returns the number of plans soft-archived.
    """
    conn = _get_conn()
    cursor = conn.execute(
        "UPDATE plans SET status = 'archived' "
        "WHERE status IN ('completed', 'failed') "
        "AND updated_at < ?",
        (cutoff,),
    )
    conn.commit()
    return cursor.rowcount


def db_archive_cleanup(cutoff: str) -> int:
    """Hard-delete archived plans older than *cutoff*.

    This is the second phase of the two-phase archive lifecycle:
    plans are first soft-archived by ``db_archive_terminal_plans()``
    and permanently removed here after the cleanup window.

    Returns the number of plans deleted.
    """
    conn = _get_conn()
    cursor = conn.execute(
        "DELETE FROM plans WHERE status = 'archived' " "AND updated_at < ?",
        (cutoff,),
    )
    conn.commit()
    return cursor.rowcount
