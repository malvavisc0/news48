# Skill: Executor agent CLI reference

## Scope
Always active — executor must only use documented commands.

Evidence commands are loaded separately in the shared evidence commands reference. This file lists executor-specific action commands only.

## Pipeline Execution Commands
- `news48 fetch --json` — fetch RSS/Atom feeds, insert article metadata.
- `news48 download --json` — download full HTML content for articles. Supports `--feed` and `--limit`; current default batch size is 50 when `--limit` is omitted.

## Article Mutation Commands
- `news48 articles info IDENTIFIER --json` — inspect one article state.
- `news48 articles check IDENTIFIER --claims-json '<JSON_ARRAY>' --result "..." --json` — persist fact-check claims.
- `news48 articles fail ARTICLE_ID --json` — mark article as failed.
- `news48 articles delete IDENTIFIER --json` — delete an article.
- `news48 articles feature IDENTIFIER --json` — mark article as featured.
- `news48 articles breaking IDENTIFIER --json` — mark article as breaking news.

## Feed and Plan Mutation Commands
- `news48 feeds add URL --json` — add a new feed.
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
