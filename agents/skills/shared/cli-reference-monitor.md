# Skill: Monitor agent CLI reference

## Scope
Always active — monitor must only use documented commands.

Evidence commands are loaded separately in the shared evidence commands reference. This file lists monitor-specific permissions and restrictions only.

## Email
Monitor can send email when SMTP is configured. No CLI commands are needed for email delivery — it is handled by the `send_email` tool.

## Forbidden Commands
Monitor must NOT run:
- `news48 fetch`, `news48 download`, `news48 parse`
- `news48 feeds add`, `news48 feeds update`, `news48 feeds delete`
- `news48 seed`
- `news48 articles update`, `news48 articles delete`, `news48 articles feature`, `news48 articles breaking`
- `news48 plans cancel`, `news48 plans remediate`
- `news48 cleanup purge`
- `news48 agents start`, `news48 agents stop`, `news48 agents dashboard`
- `news48 feeds rss`, `news48 sitemap generate`

## Selection Heuristic
1. Use `news48 stats --json` first for a broad system snapshot.
2. Use `news48 feeds list --json` and `news48 fetches list --json` for freshness assessment.
3. Use `news48 articles list --status fact-unchecked --json` and `news48 articles list --status fact-checked --json` for fact-check backlog and recent throughput review.
4. Use `news48 cleanup health --json` to evaluate database health.
5. Use `news48 logs list --json` when investigating anomalies.
