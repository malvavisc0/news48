# Skill: Health thresholds reference

## Scope
Always active for monitor and planner agents — single source of truth for all health thresholds.

## Thresholds

| Metric | Warning | Critical |
|--------|---------|----------|
| Database size | 100 MB | 500 MB |
| Feed stale | 7 days | 14 days |
| Download failure rate | 10% | 25% |
| Parse failure rate | 10% | 25% |
| Articles older than 48h | present | 100+ |
| Empty article backlog | 50 | 200 |
| Downloaded backlog | 50 | 200 |

## Classification
Compute strictly in this order:
1. `CRITICAL` if any critical threshold is breached
2. `WARNING` if no critical but one or more warning thresholds are breached
3. `HEALTHY` otherwise

## Rules
- Use only metrics exposed by documented CLI output.
- If a denominator is zero or a metric cannot be proved from current evidence, call that out explicitly instead of inferring.
- Do not duplicate these thresholds in other skills or instructions — this is the canonical source.