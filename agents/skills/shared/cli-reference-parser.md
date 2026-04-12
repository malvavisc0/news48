# Skill: Parser agent CLI reference

## Scope
Always active — parser must only use documented commands.

## Core Rules
1. Only use commands listed here. Do not invent commands, subcommands, flags, or statuses.
2. Always pass `--json` to every `news48` command.
3. Pass `--json` as a CLI flag, not as a tool parameter.

## Commands

### Article Update
- `news48 articles update ARTICLE_ID --content-file /tmp/parsed_ARTICLEID.txt --json` — update article with parsed content. Sets `parsed_at` automatically when content-file is provided.

### Verification
- `news48 articles info IDENTIFIER --json` — verify `parsed_at` is set after update.

### Failure Reporting
- `news48 articles fail ARTICLE_ID --error "reason" --json` — mark article as parse-failed with error reason.

### Re-download Corrupted or Empty Content
If the HTML file is corrupt or empty, re-download the article content:
- `news48 download --article ARTICLE_ID --json` — download HTML for a specific article by ID.
- After re-download, re-read the HTML file path provided in the task.

### Evidence (rarely needed)
- `news48 stats --json` — broad system snapshot. Rarely needed; the parser operates on one pre-assigned article.

## Forbidden Commands
Parser must NOT run:
- `news48 fetch`, `news48 parse`
- `news48 feeds add`, `news48 feeds update`, `news48 feeds delete`
- `news48 seed`
- `news48 plans list`, `news48 plans show`, `news48 plans remediate`, `news48 plans cancel`
- `news48 articles delete`, `news48 articles feature`, `news48 articles breaking`, `news48 articles check`
- `news48 cleanup purge`
- `news48 agents start`, `news48 agents stop`, `news48 agents dashboard`
- `news48 feeds rss`, `news48 sitemap generate`