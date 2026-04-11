# Skill: send-email

## Trigger
Conditional — active when status is WARNING or CRITICAL.

## Rules
Use `send_email` with:
- `subject`: `[news48] Monitor Report - <status>`
- For CRITICAL: append ` [URGENT]`
- `body`: Full report text
- `to`: Leave empty to use `MONITOR_EMAIL_TO` env var

## Decision Table
| Status | Email Action |
|--------|--------------|
| `HEALTHY` | Do not send unless explicitly requested |
| `WARNING` | Send report |
| `CRITICAL` | Send report with `[URGENT]` |

## Report Format
1. Overall Status
2. Metrics Summary
3. Alerts (severity, description, reasoning)
4. Recommendations (concrete actions with commands)
