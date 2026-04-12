# Skill: Start planning with evidence

## Scope
Always active — planner must start each cycle with evidence gathering.

## Rules
1. Read the latest Monitor report from `.monitor/latest-report.json` using `read_file`. If it exists, note the status and recommendations before gathering your own evidence.
2. Run `news48 stats --json` first to get a full system overview.
3. Read system state through real evidence before deciding that work is missing.
4. If `feeds.total` is 0, bootstrap the system by running `news48 seed seed.txt --json` before concluding that no work exists.
5. When bootstrapping is required, do not create a verification-only or empty-state plan. Seeding is the required action.
6. After bootstrapping, continue the cycle with refreshed evidence rather than exiting as a no-op.
7. Run `news48 plans remediate --apply --json` when plan corruption or blocked parents are present.
8. Check existing pending and executing plans with `news48 plans list --json`.
9. Identify unmet goals without duplicate work.
