# Skill: fail-safely

## Trigger
Always active — stop loops, avoid duplicate work, exit deterministically.

## Rules
1. If `claim_plan` returns `no_eligible_plans`, exit immediately.
2. Never retry the same failed action more than twice.
3. After writing terminal plan status (`completed`/`failed`), stop — do not call update tools again.
4. Never fabricate plan IDs, step IDs, or article IDs.
5. Break loops after 5 repeated tool errors with the same signature.
