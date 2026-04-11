# Skill: write-conditions

## Trigger
Always active — planner must define success conditions before steps.

## Rules
1. Always define `success_conditions` before writing plan steps.
2. Conditions are **outcome statements**, not activity statements.
3. Include 2-5 conditions per plan.
4. Use percentages for rates (`>= 75%`), absolute counts (`All 55 feeds`), zero-presence checks for cleanup.

## Good Patterns
- `All target feeds have last_fetched_at within last 120 minutes`
- `No articles remain in empty status`
- `Download success rate >= 75%`

## Bad Patterns
- ~~`Run fetch command`~~ (activity)
- ~~`Try to improve downloads`~~ (vague)
- ~~`Check things look healthy`~~ (not measurable)

## Thresholds
| Metric | Warning | Critical |
|--------|---------|----------|
| DB size | 100 MB | 500 MB |
| Feed stale | 7 days | 14 days |
| Download failure rate | 10% | 25% |
| Parse failure rate | 10% | 25% |
| Articles older than 48h | present | 100+ |
