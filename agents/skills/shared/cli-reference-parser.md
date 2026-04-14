# Skill: Parser agent CLI reference

## Scope
Always active — parser must only use documented commands.

## Core Rules
1. Only use commands listed here. Do not invent commands, subcommands, flags, or statuses.
2. Always pass `--json` to every `news48` command.
3. Pass `--json` as a CLI flag, not as a tool parameter.
4. **Always pass ALL required metadata flags on every update.** Omitting a flag means the field stays NULL in the database. You MUST populate `--title`, `--summary`, `--categories`, `--tags`, `--countries`, and `--sentiment` on every article update — these are enforced by the quality gate and normalize-fields skills.

## Commands

### Article Update
- `news48 articles update ARTICLE_ID --content-file /tmp/parsed_ARTICLEID.txt --title "Title" --summary "Summary" --categories "world,politics" --tags "election,democracy" --countries "us,gb" --sentiment neutral --json` — update article with parsed content and all required metadata. Sets `parsed_at` automatically when content-file is provided.

#### Required flags (every update)
| Flag | Format | Source skill |
|------|--------|-------------|
| `--content-file` | Path to temp file with rewritten content | stage-file, rewrite-content |
| `--title` | 8-140 chars, descriptive, no clickbait | normalize-fields, enforce-quality |
| `--summary` | 40-420 chars, 1-3 sentences, not duplicate of title | normalize-fields, enforce-quality |
| `--categories` | Comma-separated, from controlled set, 1-3 values | normalize-fields, enforce-quality |
| `--tags` | Comma-separated, lowercase, 2-8 values | normalize-fields, enforce-quality |
| `--countries` | Comma-separated ISO-2 lowercase codes only | normalize-fields, enforce-quality |
| `--sentiment` | One of: positive, negative, neutral | normalize-fields, enforce-quality |

#### Optional flags (pass when source provides signals)
| Flag | Format | When to use |
|------|--------|-------------|
| `--image-url` | URL string | Source provides a image related to the article |
| `--language` | ISO 639-1 code | Article language differs from feed default |
| `--published-at` | Date string | Parser found a better publication date |

**Important:** If you omit a required flag, the field remains NULL in the database. The quality gate requires all required fields to be populated. Always include every required flag in your update command.

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