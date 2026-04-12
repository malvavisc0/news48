# Skill: Monitor agent CLI reference

## Scope
Always active — monitor must only use documented commands.

## Core Rules
1. Only use commands listed here. Do not invent commands, subcommands, flags, or statuses.
2. Always pass `--json` to every `news48` command.
3. Pass `--json` as a CLI flag, not as a tool parameter.
4. Choose the narrowest command that proves the claim you need to make.
5. Remember that some CLI statuses are derived views over multiple database fields.

## Evidence Commands
Use these commands to observe system state:
- `news48 stats --json` — broad system snapshot including counts, backlogs, and timestamps.
- `news48 feeds list --json` — feed freshness overview.
- `news48 fetches list --json` — recent fetch run outcomes.
- `news48 articles list --json` — article backlog by status.
- `news48 cleanup status --json` — retention policy state.
- `news48 cleanup health --json` — database health metrics.
- `news48 agents status --json` — scheduler state and running agents.
- `news48 logs list --json` — recent agent log entries.

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
6. If a needed command is not listed here, do not invent it.
