# Skill: Evaluate health thresholds

## Scope
Always active — monitor must compare metrics against thresholds to classify status.

## Thresholds Reference

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
