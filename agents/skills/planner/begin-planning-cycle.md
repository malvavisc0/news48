# Skill: Start planning with evidence

## Scope
Always active — planner must start each cycle with evidence gathering.

## Rules
1. Read the latest Monitor report from `.monitor/latest-report.json` using `read_file`. If it exists, note the status and recommendations before gathering your own evidence.
2. Check if the monitor report is stale: if the report timestamp is older than 2x the monitor interval (default 10 minutes), the report may be outdated. In this case, gather your own evidence with lower confidence in the monitor's classification and note the staleness in any plans you create.
3. Run `news48 stats --json` first to get a full system overview.
4. Read system state through real evidence before deciding that work is missing.
5. If `feeds.total` is 0, bootstrap the system by running `news48 seed seed.txt --json` before concluding that no work exists.
6. When bootstrapping is required, do not create a verification-only or empty-state plan. Seeding is the required action.
7. After bootstrapping, continue the cycle with refreshed evidence rather than exiting as a no-op.
8. If `news48 seed` fails (seed file missing, network unreachable, or all seed URLs invalid), do NOT loop back to step 5. Instead, create a remediation plan with family `discovery` to investigate the bootstrap failure and recommend corrective actions (e.g., verify seed.txt exists, check network connectivity, provide alternative feed sources).
9. Run `news48 plans remediate --apply --json` when plan corruption, blocked parents, or stalled throughput are present. If pending plans exist but the executor reports "no eligible plans" in recent logs, this is a parent-chain deadlock — remediation will clear it.
10. Check existing pending and executing plans with `news48 plans list --json`.
11. Identify unmet goals without duplicate work.
