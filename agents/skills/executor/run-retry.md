# Skill: Execute retry plans

## Scope
Active when plan family is retry.

**Important**: Most download and parse failures are permanent (paywalled content, quality gate rejections, blocked domains, empty pages). Retry plans should only be created for transient issues. If a retry plan exists, execute it but apply strict limits.

## Rules
1. **List failed articles**: `news48 articles list --status download-failed --json` and `news48 articles list --status parse-failed --json`
2. **Group by domain**: Identify domains with failures and counts.
3. **Retry downloads**: `news48 download --feed <domain> --retry --json`
4. **Do NOT retry parse-failed articles**: Parse failures are almost always permanent (quality gate, fidelity, content issues). Re-parsing produces the same result. Mark parse-retry steps as skipped with reason "parse failures are permanent — investigate feed health instead".
5. **Verify**: Reduced failure counts after retry attempts.
6. **Retry limits**: Up to 3 attempts total per domain. After 3 failed attempts in the same domain within a single plan execution, skip that domain and mark its remaining steps as failed.

## Consecutive Failure Tracking
- Within a single retry plan, count how many download attempts per domain have failed. If a domain fails 3 times in the same plan, stop retrying it.
- When marking a domain as skipped, include the domain name and failure count in the step result: `"skipped: <domain> failed 3/3 attempts"`.
- If most domains in a retry plan fail, complete the plan as failed and note that feed health investigation is needed instead of more retries.
