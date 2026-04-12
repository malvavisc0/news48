# Skill: Read the latest monitor report

## Scope
Always active — planner must check the Monitor's latest report before deciding what work to create.

## Rules
1. Check if `.monitor/latest-report.json` exists. 
 1.1. If exists:
    - Read the latest monitor report using `read_file` on `.monitor/latest-report.json`.
    - Use the `recommendations` array to identify work the Monitor has flagged.
 1.2. If the file does not exist or is empty, proceed with evidence gathering as usual — the Monitor may not have run yet.
4. Prioritize Monitor recommendations alongside evidence from `news48 stats --json` and `news48 plans list --json`.
5. Do not create a plan that duplicates a Monitor recommendation already covered by an existing plan.
6. If the Monitor status is `CRITICAL`, treat its recommendations as high-priority goals.
7. If the Monitor status is `WARNING`, incorporate its recommendations into the normal prioritization cycle.
8. If the Monitor status is `HEALTHY`, note it in the cycle summary but do not create plans based on a healthy report.