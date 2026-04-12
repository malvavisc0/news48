# Skill: Build minimal executable plans

## Scope
Always active — planner creates execution plans.

## Rules
1. Create one step per domain for download and parse work.
2. Steps must be natural language descriptions.
3. End every plan with a verification step.
4. Write the minimum plans needed — do not over-plan.
5. Use `parent_id` for sequential dependencies.
6. NEVER include specific CLI commands in step descriptions.
7. Steps must be verb-oriented natural language describing WHAT, not HOW.
8. Success conditions are governed by [`agents/skills/planner/write-conditions.md`](agents/skills/planner/write-conditions.md); do not duplicate or weaken that policy here.
9. If evidence shows bootstrap is required, follow [`agents/skills/planner/begin-planning-cycle.md`](agents/skills/planner/begin-planning-cycle.md) instead of creating a placeholder plan.
10. Do not create observational plans that merely confirm emptiness, idleness, or health without changing or unblocking anything.
