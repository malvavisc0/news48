# Skill: Respond to throughput emergencies

## Scope
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

## Historical Comparison Procedure
To determine if backlog is non-improving across cycles:

1. Read the most recent metrics file from `.metrics/` directory:
   ```bash
   ls -t .metrics/*.json 2>/dev/null | head -1
   ```
2. If a previous metrics file exists, read it with `read_file` and extract the `parse_backlog` and `download_backlog` values.
3. Compare with current cycle values from `news48 stats --json`:
   - **Non-improving**: current backlog >= previous backlog for both parse and download
   - **Improving**: current backlog < previous backlog for either parse or download
4. If no previous metrics file exists, this is the first cycle — do not trigger emergency yet. Record current values and check again next cycle.
