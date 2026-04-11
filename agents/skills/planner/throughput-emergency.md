# Skill: throughput-emergency

## Trigger
Conditional — active when backlog > 200 and non-improving.

## Rules
When throughput collapses (no articles transitioning empty->downloaded->parsed):

1. **Only plan these goals**:
   - Feed freshness
   - Article completeness
   - Article parsing

2. **Defer**: retention, feed health, DB optimization, broad fact-check expansion.

3. **Exit when**: both backlog conditions are false for one full cycle.

## Trigger Conditions
- `parse_backlog` or `download_backlog` > 200 from `news48 stats --json`
- Backlog non-improving across two consecutive cycles
