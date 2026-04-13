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
5. **Deadlock detection**: If `news48 plans list --status pending --json` returns plans AND the executor consistently reports "no eligible plans" (check executor logs), this indicates a parent-chain deadlock. Run `news48 plans remediate --apply --json` to clear blocked parent references.
6. If remediation does not resolve the deadlock, cancel the deadlocked plans and create fresh execution plans WITHOUT `parent_id` links to campaigns.

Do not create a remediation plan when the stale condition clears during the current planning cycle.
