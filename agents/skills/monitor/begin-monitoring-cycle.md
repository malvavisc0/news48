# Skill: Start monitoring with evidence

## Scope
Always active — monitor must gather evidence, classify status, and report findings in every cycle.

## Workflow

### Step 1: Gather Evidence
Always run these commands before making any classification:
1. `news48 stats --json` — system snapshot (backlogs, failure rates, article counts)
2. `news48 cleanup health --json` — database size and integrity
3. `news48 cleanup status --json` — retention policy state
4. `news48 feeds list --json` — feed freshness overview
5. `news48 fetches list --json` — recent fetch run outcomes
6. `news48 articles list --status fact-unchecked --json` — fact-check backlog
7. `news48 articles list --status fact-checked --json` — recent fact-check completions

Use `news48 logs list --json` only when investigating specific anomalies.

### Step 2: Compute Rates
Use only fields present in `news48 stats --json` article metrics:
- Download failure rate = `download_failures / (download_failures + parse_backlog + parsed)` when denominator > 0
- Parse failure rate = `parse_failures / (parse_failures + parsed)` when denominator > 0

If denominator is 0, rate is 0. Note "insufficient sample" — do not extrapolate.

### Step 3: Compare Against Thresholds
Use the **thresholds** skill for the canonical threshold table. Compare each computed metric against those values.

### Step 4: Classify Status
Use the classification rules in the **thresholds** skill.

### Step 5: Generate Report
Structure the output as:
1. **Overall Status** — HEALTHY / WARNING / CRITICAL with breach count
2. **Metrics Summary** — key numbers (backlogs, failure rates, oldest items)
3. **Alerts** — each alert: severity, description, reasoning (cite CLI evidence)
4. **Recommendations** — concrete next steps for Planner/Executor

### Step 6: Persist Report
Write the report to `.monitor/latest-report.json` using the `write-monitor-report` skill. This file is read by the Planner at the start of each planning cycle.

### Step 7: Persist Metrics History
Write a timestamped metrics file to `.metrics/` using the `write-metrics-history` skill. This enables trend analysis across cycles.

### Step 8: Send Email (if configured and status is WARNING or CRITICAL)
- Use `send_email` tool (not CLI)
- Subject: `[news48] Monitor Report - <status>` + `[URGENT]` for CRITICAL
- Body: Full report text from Step 5
- `to`: Leave empty to use `MONITOR_EMAIL_TO` env var

Do not send email when status is HEALTHY unless explicitly requested.

## Rules
- Always cite actual CLI output as evidence. Never guess numbers.
- Recommend actions for Planner/Executor — do not execute them yourself.
- If email is unavailable, state that clearly in the output.
- Use threshold-based language for external signals; avoid absolute claims when remote systems can fail.
- If a branch condition is discovered mid-cycle (breach found, alerts needed, fact-check drift found), follow the matching skill in the same run.
