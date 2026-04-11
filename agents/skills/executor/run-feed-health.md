# Skill: run-feed-health

## Trigger
Active when plan family is feed-health.

## Rules
1. **List all feeds**: `news48 feeds list --json`
2. **Identify stale feeds**: `last_fetched_at` beyond 7 days threshold.
3. **Re-fetch stale feeds**: `news48 fetch --json` for each stale feed.
4. **Verify**: All feeds have `last_fetched_at` within threshold.
