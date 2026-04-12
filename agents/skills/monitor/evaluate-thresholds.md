# Skill: Evaluate health thresholds

## Scope
Always active — monitor must compare metrics against thresholds to classify status.

## Thresholds Reference
Use the **thresholds** skill for the canonical threshold table and classification rules. This skill provides the evaluation procedure only.

## Evaluation Procedure
1. Gather metrics from CLI evidence.
2. Compare each metric against the thresholds defined in the **thresholds** skill.
3. Classify using the rules in the **thresholds** skill.
4. Note "insufficient sample" when a denominator is 0 — do not extrapolate.
