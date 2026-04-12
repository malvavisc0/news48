# Skill: Execute feed health plans

## Trigger
Active when plan family is feed-health.

## Rules
1. **List all feeds**: `news48 feeds list --json`
2. **Identify stale feeds**: `last_fetched_at` beyond 7 days threshold.
3. **Re-fetch stale feeds**: `news48 fetch --json` for each stale feed.
4. **Verify**: use threshold-based outcomes such as critical stale-feed reduction or ≥90% freshness, not absolute recovery of every feed.
