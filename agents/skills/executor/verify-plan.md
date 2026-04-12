# Skill: Verify plan completion with evidence

## Scope
Always active — executor must verify outcomes against success conditions.

## Rules
1. The final step verifies completion against the plan's `success_conditions`.
2. Validate each condition before evaluating it.
3. Run evidence CLI commands and evaluate every valid condition.
3. Record results in this format:
   ```
   PASS: <condition> -- evidence: <CLI output>
   FAIL: <condition> -- evidence: <CLI output>
   INVALID: <condition> -- reason: <policy/schema/evidence problem>
   ```
4. Mark plan `completed` only when ALL valid conditions pass and no invalid conditions exist.
5. Mark plan `failed` when verification is complete and valid conditions are not met.
6. If any condition is invalid, fail the plan as a plan-quality defect rather than claiming execution alone failed.

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

## Invalid Condition Checks
- Uses a field, status, or metric not exposed by the system.
- Requires zero-tolerance success for external operations.
- Cannot be proven with documented evidence commands.
- Confuses derived status with guaranteed persisted state.
