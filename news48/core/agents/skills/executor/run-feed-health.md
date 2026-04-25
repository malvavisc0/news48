# Skill: Execute feed health plans

## Scope
Active when plan family is feed-health.

## Rules
1. **List all feeds**: `news48 feeds list --json`
2. **Identify stale feeds**: `last_fetched_at` beyond the configured threshold (see thresholds skill).
3. **Re-fetch stale feeds**: `news48 fetch --feed DOMAIN --json` for each stale feed (e.g. `news48 fetch --feed reuters.com --json`). Use `--feed`, not `--feed-url`.
4. **Verify**: use threshold-based outcomes such as critical stale-feed reduction or ≥90% freshness, not absolute recovery of every feed.
