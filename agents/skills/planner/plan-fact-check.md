# Skill: Create fact-check coverage plans

## Scope
Conditional — active when fact-check backlog exists.

## Rules
1. **Eligibility**: articles that are `parsed`, `fact-unchecked`, in priority categories: politics, health, science, conflict.
2. **Mandatory trigger**: if eligible candidates exist and no pending/executing fact-check plan covers them, create one.
3. **Throughput floor**: target at least 3 items when 3+ available.
4. **Anti-starvation**: if backlog exists for 2 consecutive cycles, fact-check takes precedence over low-priority goals.
5. **Policy window**: use bounded completion windows such as completion within 24 hours for eligible covered items.
6. Do not assume all parsed articles are fact-check eligible; use observed fields and documented priority rules.
