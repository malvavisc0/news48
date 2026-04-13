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
7. `parent_id` is a BLOCKING dependency — the executor will NOT claim the child until the parent is completed. NEVER set `parent_id` to a campaign plan ID. Setting `parent_id` to a campaign causes a deadlock because campaigns are never completed by executors.
8. `campaign_id` is a NON-BLOCKING grouping field — use it to associate child plans with their campaign. Children with `campaign_id` can be claimed immediately.
9. NEVER include specific CLI commands in step descriptions.
10. Steps must be verb-oriented natural language describing WHAT, not HOW.
11. Success conditions must follow the condition-writing rules; do not duplicate or weaken those rules here.
12. If evidence shows bootstrap is required (`feeds.total == 0`), run `news48 seed seed.txt --json` and continue the cycle with refreshed evidence instead of creating a placeholder plan.
13. Do not create observational plans that merely confirm emptiness, idleness, or health without changing or unblocking anything, except a campaign plan that groups executable child plans.
14. If retention evidence shows expired articles, create a cleanup plan whose success conditions require zero articles older than 48 hours.
15. **Executor feedback**: Before creating or recreating plans, check `.plans/feedback/` for any INVALID condition reports from the executor. If a plan's conditions were previously marked INVALID, revise the conditions based on the feedback reason before creating a new plan.
16. **No lone campaigns**: A campaign plan MUST be followed immediately by at least one child execution plan (with `campaign_id` set to the campaign's ID) in the same planning cycle. A campaign with zero children is useless — it will be auto-failed by remediation.
17. **Fetch-all → single execution plan**: For fetch operations covering all feeds, create a single execution plan with `scope_type=all_feeds` — do NOT wrap it in a campaign. Campaigns are only for broad download or parse backlogs that span many independent feeds requiring separate tracking.
18. **When in doubt, prefer execution over campaign**: Only use `plan_kind=campaign` when you genuinely need to group multiple independent feed-scoped child plans. A single operation (fetch-all, cleanup, db-health) should always be `plan_kind=execution`.

## Campaign Example — CORRECT
1. `create_plan(task="Download campaign...", plan_kind="campaign")` → returns id `"abc-123"`
2. `create_plan(task="Download articles from feed X", campaign_id="abc-123")` ← uses `campaign_id`
3. `create_plan(task="Download articles from feed Y", campaign_id="abc-123")` ← uses `campaign_id`

## Campaign Example — WRONG (causes deadlock)
1. `create_plan(task="Download campaign...", plan_kind="campaign")` → returns id `"abc-123"`
2. `create_plan(task="Download articles from feed X", parent_id="abc-123")` ← DEADLOCK! Child can never be claimed because the campaign parent is never completed.
