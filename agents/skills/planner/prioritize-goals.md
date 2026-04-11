# Skill: prioritize-goals

## Trigger
Always active — planner must prioritize goals in correct order.

## Goal Priority Order
| # | Goal | Target State |
|---|------|-------------|
| 1 | Feed freshness | All feeds fetched within last 120 min |
| 2 | Article completeness | All `empty` articles covered by download plan |
| 3 | Article parsing | All `downloaded` articles covered by parse plan |
| 4 | Failure recovery | Retry failed articles up to 3 times |
| 5 | Fact-check coverage | Eligible articles covered within 1 cycle, completed in 24h |
| 6 | Stuck plan remediation | No plan requeued more than twice |
| 7 | Retention compliance | No articles older than 48h |
| 8 | Feed health | No feeds stale beyond 7 days |
| 9 | Database health | DB size under 100MB, integrity OK |
