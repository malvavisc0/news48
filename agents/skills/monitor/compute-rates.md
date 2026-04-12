# Skill: Compute monitoring rates

## Scope
Always active — monitor must apply fixed formulas for failure rates.

## Rules
Use only fields that actually exist in `news48 stats --json`.

From `news48 stats --json` article metrics:
- download attempt denominator = `download_failures + parse_backlog + parsed`
- download failure rate = `download_failures / (download_failures + parse_backlog + parsed)` when denominator > 0
- parse attempt denominator = `parse_failures + parsed`
- parse failure rate = `parse_failures / (parse_failures + parsed)` when denominator > 0

If a denominator is 0, treat the rate as 0 and explicitly note `insufficient sample`.

Do not invent helper fields such as `with_text` or `no_text` if they are not present in the CLI payload.
