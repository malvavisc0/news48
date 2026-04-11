# Skill: begin-monitoring-cycle

## Trigger
Always active — monitor must gather baseline metrics first.

## Rules
1. Run `news48 stats --json`
2. Check `news48 cleanup health --json`
3. Check `news48 cleanup status --json`
4. Review `news48 feeds list --json`
5. Scan for backlogs and failures
6. Classify and report alerts
7. Provide actionable recommendations
