# Skill: Report parsing failure clearly

## Scope
Conditional — active when quality gate or fidelity failure occurs.

## Rules
1. Run quality gate checks before final update.
2. If any check fails, fail fast with explicit reason code.
3. Use: `uv run news48 articles fail ARTICLEID --error "parse.<reason_code>: Failed parser quality gate: <reason>" --json`
