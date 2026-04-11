# Skill: evaluate-thresholds

## Trigger
Always active — monitor must compare metrics against thresholds.

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
