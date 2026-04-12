# Skill: Use only documented CLI commands

> **Note**: This file is a general reference and is **not loaded at runtime** by any agent.
> Each agent loads its own restricted CLI reference (e.g. `cli-reference-planner.md`)
> via the `SKILL_REGISTRY`. Keep this file in sync with the agent-specific files for
> documentation purposes only.

## Scope
Always active — all agents must know which CLI commands exist and how to invoke them.

## Core Rules
1. Only use commands listed here. Do not invent commands, subcommands, flags, fields, or statuses.
2. Always pass `--json` to every `news48` command except those explicitly listed as no-JSON commands.
3. Pass `--json` as a CLI flag, not as a tool parameter.
4. Choose the narrowest command that proves the claim you need to make.
5. Remember that some CLI statuses are derived views over multiple database fields rather than one stored status column.

## Evidence Commands
Use these commands to observe state:
- `news48 stats --json` — broad system snapshot.
- `news48 plans list --json` / `news48 plans show PLAN_ID --json` — plan queue and plan details.
- `news48 feeds list --json` / `news48 feeds info IDENTIFIER --json` — feed freshness and feed details.
- `news48 fetches list --json` — recent fetch runs.
- `news48 articles list --json` / `news48 articles info IDENTIFIER --json` / `news48 articles content IDENTIFIER --json` — article backlog, item details, stored content.
- `news48 cleanup status --json` / `news48 cleanup health --json` — retention and DB health.
- `news48 agents status --json` / `news48 logs list --json` / `news48 search search QUERY --json` — scheduler, logs, and search when needed.

## Execution Commands
Use pipeline commands when your role permits state changes:
- `news48 fetch --json`
- `news48 download --json`
- `news48 parse --json`

## Mutation Commands

### Articles
Use article mutation commands when your role permits them:
- `news48 articles update ARTICLE_ID --json`
- `news48 articles check IDENTIFIER --json`
- `news48 articles fail ARTICLE_ID --json`
- `news48 articles reset IDENTIFIER --json`
- `news48 articles delete IDENTIFIER --json`
- `news48 articles feature IDENTIFIER --json`
- `news48 articles breaking IDENTIFIER --json`

### Feeds and plans
Other state-changing commands:
- `news48 feeds add URL --json`
- `news48 feeds update IDENTIFIER --json`
- `news48 feeds delete IDENTIFIER --json`
- `news48 seed FILE --json`
- `news48 plans cancel PLAN_ID --json`
- `news48 plans remediate --json` — preview repairs
- `news48 plans remediate --apply --json` — apply repairs
- `news48 cleanup purge --json`

## Commands Without `--json`
Do not pass `--json` to these commands:
- `news48 feeds rss`
- `news48 sitemap generate`
- `news48 agents start`
- `news48 agents dashboard`
- `news48 agents stop`

## Selection Heuristic
1. Use snapshot commands first for broad state: `stats`, `plans list`, `feeds list`, `articles list`.
2. Use item inspection commands second for details: `plans show`, `feeds info`, `articles info`.
3. Use mutation commands only when your role is allowed to change state.
4. If a needed command or flag is not listed here, do not invent it.
