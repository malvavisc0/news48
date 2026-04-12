# Skill: Execute fact-check plans

## Trigger
Active when plan family is fact-check.

## Rules
1. **Select articles deterministically**: Use IDs from plan steps. If not provided, run `news48 articles list --status fact-unchecked --json` and select lowest IDs first.
2. **Valid statuses**: `download-failed`, `downloaded`, `empty`, `fact-checked`, `fact-unchecked`, `parse-failed`, `parsed`. Never use `priority`.
3. **Read content**: `news48 articles content <id> --json`
4. **Extract claims**: 2-5 factual claims per article (numbers, events, quotes, dates).
5. **Search evidence**: `perform_web_search` with neutral language.
6. **Fetch verification pages**: `fetch_webpage_content` on promising sources.
7. **Record verdict**: `news48 articles check <id> --status <verdict> --result "<summary>" --json`

## Verdict Values
| Status | When to Use |
|--------|-------------|
| `verified` | 2+ independent sources corroborate |
| `disputed` | Reliable sources contradict |
| `unverifiable` | Cannot find evidence |
| `mixed` | Some verified, others not |

## Constraints
- Require 2+ independent sources before `verified`.
- Bounded retries: up to 2 additional attempts per claim path.
- Never skip selected targets silently.
- Never assign verdict without searching for evidence first.
