# Skill: Generate monitoring alerts

## Scope
Conditional — active when threshold is breached.

## Rules
Generate one alert per distinct breached metric or policy breach.

Each alert includes: severity, metric, description, reasoning, and cited evidence.

| Severity | When to Use |
|----------|-------------|
| **warning** | Warning threshold breached without any critical breach for that metric |
| **critical** | Critical threshold breached or policy window exceeded |

Do not emit `info` alerts for healthy observations. Healthy metrics belong in the report summary, not the alerts section.

If multiple signals describe the same underlying issue, combine them into one alert with all supporting evidence rather than duplicating alerts.
