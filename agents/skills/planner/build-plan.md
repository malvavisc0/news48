# Skill: Build minimal executable plans

## Scope
Always active — planner creates execution plans.

## Rules
1. For broad download backlog, create one lightweight campaign plan plus child execution plans scoped to individual feeds/domains.
2. Each feed/domain download child plan should cover one feed only.
3. Campaign plans are for visibility and grouping; feed child plans are the executable work units.
4. Steps must be natural language descriptions.
5. End every execution plan with a verification step.
6. Write the minimum plans needed — do not over-plan.
7. Use `parent_id` only for true execution dependencies, not for non-blocking campaign grouping.
8. NEVER include specific CLI commands in step descriptions.
9. Steps must be verb-oriented natural language describing WHAT, not HOW.
10. Success conditions are governed by [`agents/skills/planner/write-conditions.md`](agents/skills/planner/write-conditions.md); do not duplicate or weaken that policy here.
11. If evidence shows bootstrap is required, follow [`agents/skills/planner/begin-planning-cycle.md`](agents/skills/planner/begin-planning-cycle.md) instead of creating a placeholder plan.
12. Do not create observational plans that merely confirm emptiness, idleness, or health without changing or unblocking anything, except a campaign plan that groups executable child plans.
13. If retention evidence shows expired articles, create a cleanup plan whose success conditions require zero articles older than 48 hours.
