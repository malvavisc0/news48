# Skill: verify-plan

## Trigger
Always active — executor must verify outcomes against success conditions.

## Rules
1. The final step verifies completion against the plan's `success_conditions`.
2. Run evidence CLI commands and evaluate every condition.
3. Record results in this format:
   ```
   PASS: <condition> -- evidence: <CLI output>
   FAIL: <condition> -- evidence: <CLI output>
   ```
4. Mark plan `completed` only when ALL conditions pass.
5. Mark plan `failed` when verification is complete and conditions are not met.

## Evidence Commands by Condition Type
| Condition type | Evidence command |
|---------------|-----------------|
| Feed freshness | `news48 feeds list --json` |
| Fetch error rates | `news48 stats --json` |
| Article status counts | `news48 articles list --status <status> --json` |
| Retention compliance | `news48 cleanup status --json` |
| Database health | `news48 cleanup health --json` |
| Fact-check coverage | `news48 articles list --status fact-checked --json` |
| Fact-check verdict | `news48 articles info <id> --json` |
