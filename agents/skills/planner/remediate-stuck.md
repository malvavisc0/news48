# Skill: Fix stuck plan queues

## Scope
Conditional — active when stale or requeued plans detected.

## Rules
1. Do NOT duplicate work — first check whether `news48 plans remediate --json` or stale-plan requeueing already normalized the queue.
2. Create a remediation plan only when a plan remains stale, repeatedly requeues, or fails for the same reason after recovery.
3. Treat `requeue_count >= 2` as a strong remediation trigger, not the only trigger.
4. Remediation plan steps:
   - Check system health: `news48 cleanup health --json`
   - Review executor logs: `news48 logs list --plan-id <plan_id> --json`
   - Review error patterns: `news48 logs list --agent executor --json`
   - Identify root cause (network, feed changes, resource limits)
   - Recommend corrective action

Do not create a remediation plan when the stale condition clears during the current planning cycle.
