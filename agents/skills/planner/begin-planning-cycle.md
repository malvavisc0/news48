# Skill: Start planning with evidence

## Scope
Always active — planner must start each cycle with evidence gathering.

## Rules
1. Run `news48 stats --json` first to get a full system overview.
2. Read system state through real evidence before deciding that work is missing.
3. If `feeds.total` is 0, bootstrap the system by running `news48 seed seed.txt --json` before concluding that no work exists.
4. When bootstrapping is required, do not create a verification-only or empty-state plan. Seeding is the required action.
5. After bootstrapping, continue the cycle with refreshed evidence rather than exiting as a no-op.
6. Run `news48 plans remediate --apply --json` when plan corruption or blocked parents are present.
7. Check existing pending and executing plans with `news48 plans list --json`.
8. Identify unmet goals without duplicate work.
