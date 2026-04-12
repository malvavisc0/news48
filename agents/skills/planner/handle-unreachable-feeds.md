# Skill: Handle permanently unreachable feeds

## Scope
Conditional — active when feeds have not been fetched in 30+ days.

## Rules
1. **Identify unreachable feeds**: Run `news48 feeds list --json` and check for feeds where `last_fetched_at` is null or older than 30 days.
2. **Attempt recovery**: For each unreachable feed, run `news48 fetch --feed <domain> --json` once to verify it's still unreachable.
3. **Classify**: If a feed fails 3 consecutive fetch attempts across different cycles, mark it as permanently unreachable.
4. **Create remediation plan**: For permanently unreachable feeds, create a `discovery` family plan with the goal to investigate and recommend feed replacement or removal.
5. **Do not auto-delete**: Never automatically delete feeds — always create a plan for human review.
6. **Report**: Include unreachable feed count in the monitor's evidence gathering when present.

## Error Code
Use `src.gone` for feeds that have been permanently removed, and `src.block` for feeds that block automated access.
