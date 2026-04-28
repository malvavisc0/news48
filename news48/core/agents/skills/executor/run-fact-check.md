# Skill: Execute fact-check plans

## Scope
Active when plan family is fact-check.

## Rules
1. **Select articles deterministically**: Use IDs from plan steps. If not provided, run `news48 articles list --status fact-unchecked --json` and select lowest IDs first.
2. **Fact-check eligibility**: Only `fact-unchecked` articles (parsed but not yet fact-checked) are eligible for fact-checking. Do not attempt to fact-check articles in other statuses (`empty`, `downloaded`, `download-failed`, `parse-failed`). If a plan step references an article that is not `fact-unchecked`, mark that step as failed with reason `parse.invalid_field: article not eligible for fact-check`.
3. **Read content**: `news48 articles content <id> --json`
4. **Extract claims**: 3–5 factual claims per article (hard limit: 5). Focus on numbers, events, quotes, dates.
5. **Search evidence**: `perform_web_search` with neutral language.
6. **Fetch verification pages**: `fetch_webpage_content` on promising sources.
7. **Record verdict**: Write claims JSON to `/tmp/fc-claims-<id>.json`, then run `news48 articles check <id> --claims-json-file /tmp/fc-claims-<id>.json --result "<summary>" --json`

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
