# CLI Reference for the news48 Agent

This document is the complete CLI reference for the news48 CLI agent.
All commands use the `news48` entrypoint.

## Critical Rules

1. **Always pass `--json`** for machine-readable output
2. **Never run the full pipeline at once** -- always stage by stage
3. **Always use `--force` when deleting feeds** -- the agent cannot answer interactive prompts
4. **Progress messages go to stderr** -- only JSON on stdout when `--json` is used

---

## Pipeline Stages

The pipeline has 4 stages, always run one at a time:

```
Stage 1: seed   -- Load feed URLs into the database
Stage 2: fetch  -- Fetch RSS/Atom feeds, store article metadata
Stage 3: download -- Download HTML content for articles
Stage 4: parse  -- Parse articles with LLM agent
```

---

## Commands

### `news48 seed <file> [--json]`

Load feed URLs from file into the database.

**JSON output:**
```json
{"seeded": 5, "total_urls": 20, "skipped": 15}
```

### `news48 fetch [--feed domain] [--delay 0.5] [--json]`

Fetch RSS/Atom feeds, store article metadata.

**Flags:**
- `--feed domain` -- Only fetch feeds matching this domain (e.g., `techcrunch.com`)
- `--delay seconds` -- Delay between requests (default: 0.5)
- `--json` -- Output as JSON

**JSON output:**
```json
{
  "feed_filter": "techcrunch.com",
  "feeds_fetched": 1,
  "entries": 25,
  "valid": 20,
  "success_rate": 100.0,
  "successful": [{"title": "...", "url": "...", "entries": 25, "valid": 20}],
  "failed": []
}
```

### `news48 download [--feed domain] [--limit 10] [--delay 1.0] [--retry] [--article ID] [--json]`

Download HTML content for articles that have no content.

**Flags:**
- `--feed domain` -- Only download articles from feeds matching this domain
- `--limit N` -- Maximum articles to download (default: 10)
- `--delay seconds` -- Delay between downloads (default: 1.0)
- `--retry` -- Retry articles that previously failed downloading
- `--article ID` -- Download a specific article by ID (ignores --limit, --feed, --retry)
- `--json` -- Output as JSON

**JSON output:**
```json
{
  "feed_filter": "techcrunch.com",
  "downloaded": 8,
  "failed": 2,
  "total": 10,
  "retry": false
}
```

### `news48 parse [--feed domain] [--limit 10] [--delay 1.0] [--retry] [--article ID] [--json]`

Parse articles with the LLM agent.

**Flags:**
- `--feed domain` -- Only parse articles from feeds matching this domain
- `--limit N` -- Maximum articles to parse (default: 10)
- `--delay seconds` -- Delay between parses (default: 1.0)
- `--retry` -- Retry articles that previously failed parsing
- `--article ID` -- Parse a specific article by ID (ignores --limit, --feed, --retry)
- `--json` -- Output as JSON

**JSON output:**
```json
{
  "feed_filter": "techcrunch.com",
  "parsed": 7,
  "failed": 1,
  "total": 8,
  "retry": false,
  "results": [{"title": "...", "url": "...", "success": true}]
}
```

### `news48 stats [--stale-days 7] [--json]`

Show system statistics.

**JSON output:**
```json
{
  "db_size_mb": 12.5,
  "articles": {"total": 500, "parsed": 300, "unparsed": 100, ...},
  "feeds": {"total": 15, "never_fetched": 2, "stale": 3, ...},
  "runs": {"total": 50, "last_run_at": "...", ...}
}
```

### `news48 feeds list [--limit 20] [--offset 0] [--json]`

List feeds in the database.

### `news48 feeds add <url> [--json]`

Add a feed by URL.

### `news48 feeds delete <id-or-url> [--force] [--json]`

Delete a feed. **Always pass `--force`** to skip the interactive confirmation.

### `news48 feeds info <id-or-url> [--json]`

Show feed details.

### `news48 articles list [--feed domain] [--status X] [--limit 20] [--offset 0] [--json]`

List articles with optional filters.

**Status values:**
| Status | Meaning |
|--------|---------|
| `empty` | Needs downloading |
| `downloaded` | Has content, needs parsing |
| `parsed` | Fully processed |
| `download-failed` | Download attempt failed |
| `parse-failed` | Parse attempt failed |

### `news48 articles info <id-or-url> [--json]`

Show article metadata. **Does NOT return content** (articles can be 80k+ tokens).
Returns `content_length` instead. To inspect content, use `read_file` on temp files.

---

## The `--feed` Domain Filter

The `--feed` flag accepts a **domain name** and restricts the command to feeds
matching that domain. The resolver matches against the feed URL using LIKE.

Examples:
- `news48 fetch --feed techcrunch.com --json`
- `news48 download --feed arstechnica.com --limit 20 --json`
- `news48 parse --feed bbc.com --retry --json`

If multiple feeds match the same domain, all are included.

---

## Agent Workflow: Stage by Stage

```
1. news48 stats --json              # Check overall state
2. news48 fetch --feed X --json     # Fetch a specific feed
3. news48 articles list --feed X --status empty --json  # Check what needs downloading
4. news48 download --feed X --json  # Download articles
5. news48 articles list --feed X --status downloaded --json  # Check what needs parsing
6. news48 parse --feed X --json     # Parse articles
7. news48 stats --json              # Verify results
```

**Never combine stages.** Always inspect results between stages.

---

## Background Process Spawning

For parallel operations, background shell commands and log output:

```bash
# Spawn background fetch
news48 fetch --feed techcrunch.com --json > .logs/fetch-tc.log 2>&1 & echo $!

# Spawn background download
news48 download --feed arstechnica.com --json > .logs/download-ars.log 2>&1 & echo $!

# Check if process is still running
ps -p 12345 -o pid,state,etime --no-headers 2>&1

# Read output when done
cat .logs/fetch-tc.log
```

Use `mkdir -p .logs` before first use.
