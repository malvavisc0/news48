# Skill: Send monitoring email

## Scope
Conditional — active when status is WARNING or CRITICAL **and** email is configured.

## Pre-flight Check
Before attempting to send, verify that `email_configured` is true in the task context (set by the orchestrator). If email is not configured, skip this skill entirely and note "email not configured — skipping notification" in the report output.

## Rules
Use `send_email` with:
- `subject`: `[news48] Monitor Report - <status>`
- For CRITICAL: append ` [URGENT]`
- `body`: Full report text
- `to`: Leave empty to use `MONITOR_EMAIL_TO` env var

## Decision Table
| Status | Email Action |
|--------|--------------|
| `HEALTHY` | Do not send |
| `WARNING` | Send report |
| `CRITICAL` | Send report with `[URGENT]` |

## Report Format
1. Overall Status
2. Metrics Summary
3. Alerts (severity, description, reasoning)
4. Recommendations (concrete actions with commands)
