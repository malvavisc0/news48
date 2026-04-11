# Skill: run-db-health

## Trigger
Active when plan family is db-health.

## Rules
1. **Run health check**: `news48 cleanup health --json`
2. **Get stats**: `news48 stats --json`
3. **Act**: If integrity fails or size exceeds threshold, run `news48 cleanup run --json`
4. **Verify**: Integrity passes, size under threshold.
