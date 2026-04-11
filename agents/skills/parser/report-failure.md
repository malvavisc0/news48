# Skill: report-failure

## Trigger
Conditional — active when quality gate or fidelity failure occurs.

## Rules
1. Run quality gate checks before final update.
2. If any check fails, fail fast with explicit reason code.
3. Use: `news48 articles fail ARTICLEID --error "Failed parser quality gate: <reason>" --json`
