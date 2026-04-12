# Skill: Executor agent CLI reference

## Scope
Always active — executor must only use documented commands.

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

## Pipeline Execution Commands
- `news48 fetch --json` — fetch RSS/Atom feeds, insert article metadata.
- `news48 download --json` — download full HTML content for articles. Supports `--feed` and `--limit`; current default batch size is 50 when `--limit` is omitted.
- `news48 parse --json` — reserved for the Parser agent. Executor must NOT run this; ensure downloaded articles are ready for the scheduled parser.

## Article Mutation Commands
- `news48 articles update ARTICLE_ID --json` — update article fields.
- `news48 articles check IDENTIFIER --json` — verify article processing state.
- `news48 articles fail ARTICLE_ID --json` — mark article as failed.
- `news48 articles reset IDENTIFIER --json` — reset failure flags for retry.
- `news48 articles delete IDENTIFIER --json` — delete an article.
- `news48 articles feature IDENTIFIER --json` — mark article as featured.
- `news48 articles breaking IDENTIFIER --json` — mark article as breaking news.

## Feed and Plan Mutation Commands
- `news48 feeds add URL --json` — add a new feed.
- `news48 feeds update IDENTIFIER --json` — update feed metadata.
- `news48 feeds delete IDENTIFIER --json` — delete a feed and its articles.
- `news48 seed FILE --json` — seed feeds from a text file.
- `news48 plans cancel PLAN_ID --json` — cancel a plan.
- `news48 plans remediate --json` — repair blocked or corrupted plans.

## Cleanup Commands
- `news48 cleanup purge --json` — delete articles older than retention window.

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
3. Use pipeline execution commands to drive work forward.
4. Use mutation commands only when the current plan step requires state changes.
5. If a needed command or flag is not listed here, do not invent it.
