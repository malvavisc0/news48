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
10. Success conditions must follow the condition-writing rules loaded in this prompt; do not duplicate or weaken those rules here.
11. If evidence shows bootstrap is required, follow the bootstrap procedure (rules 5–8 of the planning-cycle procedure) instead of creating a placeholder plan.
12. Do not create observational plans that merely confirm emptiness, idleness, or health without changing or unblocking anything, except a campaign plan that groups executable child plans.
13. If retention evidence shows expired articles, create a cleanup plan whose success conditions require zero articles older than 48 hours.
14. **Executor feedback**: Before creating or recreating plans, check `.plans/feedback/` for any INVALID condition reports from the executor. If a plan's conditions were previously marked INVALID, revise the conditions based on the feedback reason before creating a new plan.
