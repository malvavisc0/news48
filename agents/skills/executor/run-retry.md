# Skill: Execute retry plans

## Scope
Active when plan family is retry.

## Rules
1. **List failed articles**: `news48 articles list --status download-failed --json` and `news48 articles list --status parse-failed --json`
2. **Group by domain**: Identify domains with failures and counts.
3. **Retry downloads**: `news48 download --feed <domain> --retry --json`
4. **Retry parse-failed articles**: Create child parse plans for the failed articles. The Parser agent will process these on its schedule. Do not attempt to re-parse articles directly in the executor.
5. **Verify**: Reduced failure counts after retry attempts.
6. **Retry limits**: Follow the plan's retry limits (up to 3 attempts total). After 3 failed attempts in the same domain within a single plan execution, skip that domain and mark its remaining steps as failed.

## Consecutive Failure Tracking
The executor cannot track failures across cycles (it has no memory between runs). To handle persistent domain failures:
- Within a single retry plan, count how many download attempts per domain have failed. If a domain fails 3 times in the same plan, stop retrying it.
- When marking a domain as skipped, include the domain name and failure count in the step result so the planner can detect patterns: `"skipped: <domain> failed 3/3 attempts"`.
- The planner is responsible for cross-cycle detection: if multiple retry plans for the same domain have all failed, the planner should escalate to a `feed-health` plan instead of creating more retries.
