# Skill: run-retry

## Trigger
Active when plan family is retry.

## Rules
1. **List failed articles**: `news48 articles list --status download-failed --json` and `news48 articles list --status parse-failed --json`
2. **Group by domain**: Identify domains with failures and counts.
3. **Retry downloads**: `news48 download --feed <domain> --retry --json`
4. **Retry parses**: `news48 parse --feed <domain> --retry --json`
5. **Verify**: Reduced failure counts. No domain with more than 3 consecutive failures.
