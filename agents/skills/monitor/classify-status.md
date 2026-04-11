# Skill: classify-status

## Trigger
Always active — monitor must derive HEALTHY/WARNING/CRITICAL without subjectivity.

## Rules
Compute overall status strictly in this order:
1. `CRITICAL` if any critical threshold breached
2. `WARNING` if no critical but one+ warning thresholds breached
3. `HEALTHY` otherwise

Do not use subjective wording.
