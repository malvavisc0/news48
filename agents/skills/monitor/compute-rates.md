# Skill: compute-rates

## Trigger
Always active — monitor must apply fixed formulas for failure rates.

## Rules
From `news48 stats --json` article metrics:
- download failure rate = `download_failures / (download_failures + with_text + no_text)` when denominator > 0
- parse failure rate = `parse_failures / (parse_failures + parsed + parse_backlog)` when denominator > 0

If denominator is 0, treat rate as 0 and note "insufficient sample".
