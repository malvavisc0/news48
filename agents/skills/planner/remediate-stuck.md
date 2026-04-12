# Skill: Fix stuck plan queues

## Trigger
Conditional — active when stale or requeued plans detected.

## Rules
1. Do NOT duplicate — `claim_plan` auto-requeues stale plans.
2. If `requeue_count >= 2`, create a remediation plan.
3. Remediation plan steps:
   - Check system health: `news48 cleanup health --json`
   - Review executor logs: `news48 logs list --plan-id <plan_id> --json`
   - Review error patterns: `news48 logs list --agent executor --json`
   - Identify root cause (network, feed changes, resource limits)
   - Recommend corrective action
