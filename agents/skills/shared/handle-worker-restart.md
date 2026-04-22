# Skill: Handle worker restart

## Scope
Always active for all agents — agents must be resilient to Dramatiq worker restarts.

## Background
The Dramatiq worker process may restart at any time (e.g., Docker container restart, deployment). When this happens:
- The actor that was mid-execution is **terminated** — Dramatiq does not resume interrupted actors.
- `StartupRecoveryMiddleware.after_worker_boot()` runs recovery tasks on every worker start.
- `PlanRecoveryMiddleware.after_process()` releases plans when an actor fails with an exception.
- Workers are stateless — all scheduling state lives in Redis and plan files on disk.

## Rules for Agents
1. **Always write terminal state before exiting.** Whether a plan is marked `completed` or `failed`, an article is updated, or a report is written — persist the outcome before the actor ends. This ensures recovery middleware can detect incomplete work.
2. **Do not depend on in-memory state across restarts.** The `task_context` dict is passed once at actor start. If the worker restarts, no context is carried over. Agents must use their own CLI evidence to verify state rather than relying on stale context values.
3. **Idempotent operations only.** If an actor run is interrupted and restarted, the same work should be safe to re-execute. All pipeline commands (`fetch`, `download`, `parse`, `cleanup`) are idempotent by design.
4. **Plan claims survive restarts.** A claimed plan is owned by `executor:dramatiq-{message_id}`. If the actor fails, `PlanRecoveryMiddleware` releases the plan back to `pending` so another worker can pick it up. Stale plans (no update for 60 minutes) are requeued by `StartupRecoveryMiddleware`.
5. **Article claims survive restarts.** A claimed article remains claimed by its owner. `StartupRecoveryMiddleware` releases stale article claims on worker boot.

## What the Worker Does on Restart
1. `StartupRecoveryMiddleware.after_worker_boot()` runs:
   - `recover_stale_plans()` — resets plans stuck in `executing` by dead processes
   - `release_stale_article_claims()` — releases article claims from dead processes
   - `archive_terminal_plans()` — moves old completed/failed plans to archive
2. Workers begin consuming messages from Redis queues again.
3. `PlanRecoveryMiddleware.after_process()` monitors for actor failures and releases plans.

## Agent Implications
- If an actor was mid-execution when the worker restarted, it is lost and will be re-enqueued by the Periodiq scheduler on the next cron tick.
- No agent action is needed — the design is self-healing as long as agents follow rule 1 (write terminal state before exit).

## Terminal State Reference
- Executor: claimed plan marked `completed` or `failed`.
- Parser: article update persisted or parse failure persisted.
- Fact-checker: claims recorded and verified, or explicit failure recorded.
- Sentinel: report written and any chosen plan actions persisted.
