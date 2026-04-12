# Skill: Review fact-check coverage

## Trigger
Always active — monitor must surface fact-check backlog drift.

## Rules
Include in each cycle:
1. `news48 articles list --status fact-unchecked --json`
2. `news48 articles list --status fact-checked --json`

Report:
- Eligible fact-unchecked count in priority categories
- Fact-check completions in last 24h
- Age of oldest eligible fact-unchecked item

Raise alerts:
- `WARNING` if eligible backlog exists and completions in last 24h = 0
- `CRITICAL` if oldest eligible item exceeds 24h policy window
