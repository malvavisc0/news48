# Skill: Common evidence commands

## Scope
Always active for executor, fact_checker, and sentinel — shared evidence-gathering commands.

## Evidence Commands
Use these commands to observe system state. All agents that load this skill may run any of these:
- `uv run news48 --help` — inspect top-level CLI commands when you need to confirm real documented usage.
- `uv run news48 <command> --help` — inspect subcommand syntax before acting when documentation is unclear.
- `news48 stats --json` — broad system snapshot (backlogs, failure rates, article counts, timestamps).
- `news48 plans list --json` — pending and executing plans.
- `news48 plans show PLAN_ID --json` — plan details and step status.
- `news48 feeds list --json` — all feeds with freshness info.
- `news48 feeds info IDENTIFIER --json` — single feed details.
- `news48 fetches list --json` — recent fetch run outcomes.
- `news48 articles list --json` — article backlog by status. Supports `--status STATUS` filter.
- `news48 articles info IDENTIFIER --json` — single article details.
- `news48 articles content IDENTIFIER --json` — stored HTML content.
- `news48 cleanup status --json` — retention policy state.
- `news48 cleanup health --json` — database health metrics.
- `news48 agents status --json` — scheduler state and running agents.
- `news48 logs list --json` — recent agent log entries.

## Core Rules
1. Only use evidence commands listed here or action commands from your agent-specific CLI reference. Do not invent commands, subcommands, flags, fields, or statuses.
2. Always pass `--json` to every `news48` command.
3. Pass `--json` as a CLI flag, not as a tool parameter.
4. Choose the narrowest command that proves the claim you need to make.
5. Remember that some CLI statuses are derived views over multiple database fields.
6. If a needed command or flag is not listed here or in your agent-specific reference, do not invent it.
7. You may use safe shell commands for inspection when needed, such as reading files, checking paths, or confirming environment state, but never for destructive or scope-expanding work.
8. If `--help` reveals a real command pattern that was previously unclear, you may save that as an operational lesson.
