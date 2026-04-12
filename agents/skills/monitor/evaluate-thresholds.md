# Skill: Evaluate health thresholds

## Scope
Always active — monitor must compare metrics against thresholds to classify status.

## Evaluation Procedure
1. Gather metrics from CLI evidence.
2. Compare each metric against the canonical threshold table.
3. Classify strictly in this order: CRITICAL if any critical threshold is breached, WARNING if no critical but one or more warning thresholds are breached, HEALTHY otherwise.
4. When a denominator is 0 or a metric cannot be computed from evidence, record "insufficient sample" — do not extrapolate or treat as a zero rate.
