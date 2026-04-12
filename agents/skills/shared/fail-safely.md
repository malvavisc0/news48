# Skill: Stop safely and avoid loops

## Scope
Always active — stop loops, avoid duplicate work, exit deterministically.

## Rules
1. If `claim_plan` returns `no_eligible_plans`, exit immediately.
2. Never retry the same failed action more than twice.
3. After writing terminal state for the current unit of work, stop or move to the next explicit cycle boundary.
4. Never fabricate plan IDs, step IDs, or article IDs.
5. Break loops after 5 repeated tool errors with the same signature.
