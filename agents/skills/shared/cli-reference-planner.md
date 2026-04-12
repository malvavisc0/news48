# Skill: Planner agent CLI reference

## Scope
Always active — planner must only use documented commands.

## Core Rules
1. Only use commands listed here. Do not invent commands, subcommands, flags, fields, or statuses.
2. Always pass `--json` to every `news48` command.
3. Pass `--json` as a CLI flag, not as a tool parameter.
4. Choose the narrowest command that proves the claim you need to make.
5. Remember that some CLI statuses are derived views over multiple database fields.

## Evidence Commands
Use these commands to observe system state:
- `news48 stats --json` — broad system snapshot.
- `news48 plans list --json` — pending and executing plans.
- `news48 plans show PLAN_ID --json` — plan details and step status.
- `news48 feeds list --json` — all feeds with freshness info.
- `news48 feeds info IDENTIFIER --json` — single feed details.
- `news48 fetches list --json` — recent fetch run outcomes.
- `news48 articles list --json` — article backlog by status.
- `news48 articles info IDENTIFIER --json` — single article details.
- `news48 articles content IDENTIFIER --json` — stored HTML content.
- `news48 cleanup status --json` — retention policy state.
- `news48 cleanup health --json` — database health metrics.
- `news48 agents status --json` — scheduler state.
- `news48 logs list --json` — recent agent log entries.

## Plan Management Commands
- `news48 plans remediate --json` — repair blocked or corrupted plans.

## Bootstrap Command
- `news48 seed FILE --json` — insert feed URLs from a text file. Use only when `feeds.total` is 0.

## Forbidden Commands
Planner must NOT run:
- `news48 fetch`, `news48 download`, `news48 parse` (executor work)
- `news48 feeds add`, `news48 feeds update`, `news48 feeds delete`
- `news48 articles update`, `news48 articles delete`, `news48 articles feature`, `news48 articles breaking`
- `news48 cleanup purge`
- `news48 agents start`, `news48 agents stop`, `news48 agents dashboard`
- `news48 feeds rss`, `news48 sitemap generate`

## Selection Heuristic
1. Run `news48 stats --json` first for a full system overview.
2. Use `news48 plans list --json` to check for existing active plans before creating new ones.
3. Use `news48 feeds list --json` and `news48 articles list --json` to identify backlog.
4. If `feeds.total` is 0, bootstrap with `news48 seed` instead of creating observation-only plans.
5. If a needed command is not listed here, do not invent it.