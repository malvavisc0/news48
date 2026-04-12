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
| Fact-check completions (24h) | < 1 with backlog | 0 with backlog |
| Fact-check oldest eligible item | > 12h | > 24h |

## Rate Denominator Semantics
All failure rates in this table are computed as **lifetime rates** (since system initialization), not per-cycle or per-24h rates. The denominator includes all articles processed since the system started.

If a denominator is zero, the rate is **undefined** (not 0%). Undefined rates must not trigger threshold breaches — record them as `null` with an "insufficient sample" note.

## Classification
Compute strictly in this order:
1. `CRITICAL` if any critical threshold is breached
2. `WARNING` if no critical but one or more warning thresholds are breached
3. `HEALTHY` otherwise

## Rules
- Use only metrics exposed by documented CLI output.
- If a denominator is zero or a metric cannot be proved from current evidence, call that out explicitly instead of inferring.
- Do not duplicate these thresholds in other skills or instructions — this is the canonical source.