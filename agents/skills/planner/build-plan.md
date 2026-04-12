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
10. Success conditions must follow the condition-writing rules; do not duplicate or weaken those rules here.
11. If evidence shows bootstrap is required (`feeds.total == 0`), run `news48 seed seed.txt --json` and continue the cycle with refreshed evidence instead of creating a placeholder plan.
12. Do not create observational plans that merely confirm emptiness, idleness, or health without changing or unblocking anything, except a campaign plan that groups executable child plans.
13. If retention evidence shows expired articles, create a cleanup plan whose success conditions require zero articles older than 48 hours.
14. **Executor feedback**: Before creating or recreating plans, check `.plans/feedback/` for any INVALID condition reports from the executor. If a plan's conditions were previously marked INVALID, revise the conditions based on the feedback reason before creating a new plan.
15. **No lone campaigns**: A campaign plan MUST be followed immediately by at least one child execution plan (with `campaign_id` set to the campaign's ID) in the same planning cycle. A campaign with zero children is useless — it will be auto-failed by remediation.
16. **Fetch-all → single execution plan**: For fetch operations covering all feeds, create a single execution plan with `scope_type=all_feeds` — do NOT wrap it in a campaign. Campaigns are only for broad download or parse backlogs that span many independent feeds requiring separate tracking.
17. **When in doubt, prefer execution over campaign**: Only use `plan_kind=campaign` when you genuinely need to group multiple independent feed-scoped child plans. A single operation (fetch-all, cleanup, db-health) should always be `plan_kind=execution`.
