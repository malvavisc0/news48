# Skill: Prioritize planner goals

## Scope
Always active — planner must prioritize goals in correct order.

## Goal Priority Order
| # | Goal | Target State |
|---|------|-------------|
| 1 | Feed freshness | ≥90% of feeds fetched within last 120 min |
| 2 | Article completeness | Eligible `empty` backlog is covered by active download work |
| 3 | Article parsing | Eligible downloaded backlog is covered by active parse work |
| 4 | Failure recovery | Retry failed articles up to 3 times |
| 5 | Fact-check coverage | Eligible articles are covered promptly with bounded completion windows |
| 6 | Stuck plan remediation | No plan requeued more than twice |
| 7 | Retention compliance | No articles older than 48h |
| 8 | Feed health | Stale-feed exposure is reduced below critical threshold |
| 9 | Database health | DB size under 100MB, integrity OK |

## Success Condition Guidelines
- Bootstrap first when there are zero feeds in the database.
- Feed freshness: ≥90% of feeds have last_fetched_at within threshold.
- Retention compliance is mandatory whenever `news48 cleanup status --json` shows one or more expired articles.
- Cleanup success conditions should require zero articles older than 48 hours after execution.
- Never require 100% success for external network resources.
- Example: "At least 90% of feeds (≥50/55) have last_fetched_at within 120 minutes"
- Coverage goals should be phrased as plan coverage or bounded backlog reduction when execution depends on external systems.

## Anti-Patterns
- Do not create a plan whose task is only to verify the system is empty.
- Do not create a plan whose success conditions only restate current state without driving work.
