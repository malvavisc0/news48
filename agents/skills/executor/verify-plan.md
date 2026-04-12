# Skill: Verify plan completion with evidence

## Scope
Always active — executor must verify outcomes against success conditions.

## Rules
1. The final step verifies completion against the plan's `success_conditions`.
2. Validate each condition before evaluating it.
3. Run evidence CLI commands and evaluate every valid condition.
4. Record results in this format:
   ```
   PASS: <condition> -- evidence: <CLI output>
   FAIL: <condition> -- evidence: <CLI output>
   INVALID: <condition> -- reason: <policy/schema/evidence problem>
   ```
5. Mark plan `completed` only when ALL valid conditions pass and no invalid conditions exist.
6. Mark plan `failed` when verification is complete and valid conditions are not met.
7. If any condition is invalid, fail the plan as a plan-quality defect rather than claiming execution alone failed. Persist the INVALID condition details to `.plans/feedback/<plan_id>.json` so the planner can read and fix them in the next cycle:
   ```bash
   mkdir -p .plans/feedback && python3 -c "
import json
feedback = {'plan_id': '<plan_id>', 'invalid_conditions': [<list of {condition, reason}>], 'timestamp': '<ISO 8601>'}
with open('.plans/feedback/<plan_id>.json', 'w') as f:
    json.dump(feedback, f, indent=2)
"
   ```
8. Before failing a batched execution plan, verify whether more command calls are still required by the plan rather than treating one partial batch as final evidence.

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
