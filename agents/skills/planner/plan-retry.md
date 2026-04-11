# Skill: plan-retry

## Trigger
Conditional — active when failed backlog exists.

## Rules
1. Retry `download-failed` and `parse-failed` articles up to **3 attempts**.
2. Apply retry limits at plan/domain scope.
3. After 3+ consecutive failures in same domain, skip and create remediation plan.
4. Never create infinite retry loops — include explicit stop conditions.
