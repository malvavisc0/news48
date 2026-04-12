# CLI Testing Guide

Manual test steps for all `news48` CLI commands. Run each test in order -- later tests depend on data from earlier ones.

## Prerequisites

```bash
# Copy .env.example to .env and configure DATABASE_PATH
cp .env.example .env
# Edit .env: set DATABASE_PATH=news48_test.db (use a test DB)

# Verify the CLI is available
uv run news48 --help
```

## 1. Seed

### 1.1 Seed -- text output
```bash
uv run news48 seed seed.txt
```
Expected: `Seeded N new feeds (M skipped, 55 total)`

### 1.2 Seed -- JSON output
```bash
uv run news48 seed seed.txt --json
```
Expected: `{"seeded": 0, "total_urls": 55, "skipped": 55}` (all skipped on second run)

### 1.3 Seed -- error: missing file
```bash
uv run news48 seed nonexistent.txt
```
Expected: error message to stderr, exit code 1

### 1.4 Seed -- error: missing file with --json
```bash
uv run news48 seed nonexistent.txt --json
```
Expected: `{"error": "..."}` to stdout, exit code 1

---

## 2. Feeds

### 2.1 Feeds list -- text output
```bash
uv run news48 feeds list
```
Expected: list of feeds with title, fetched date, and URL

### 2.2 Feeds list -- JSON output
```bash
uv run news48 feeds list --json
```
Expected: `{"total": N, "limit": 20, "offset": 0, "feeds": [...]}`

### 2.3 Feeds list -- pagination
```bash
uv run news48 feeds list --limit 3 --offset 2 --json
```
Expected: 3 feeds starting from offset 2

### 2.4 Feeds add -- text output
```bash
uv run news48 feeds add https://example.com/test-feed.xml
```
Expected: `Added feed: https://example.com/test-feed.xml (ID: N)`

### 2.5 Feeds add -- JSON output
```bash
uv run news48 feeds add https://example.com/test-feed-2.xml --json
```
Expected: `{"added": true, "id": N, "url": "..."}`

### 2.6 Feeds add -- duplicate
```bash
uv run news48 feeds add https://example.com/test-feed.xml --json
```
Expected: `{"added": false, "reason": "Feed already exists", ...}`

### 2.7 Feeds info -- text output
```bash
uv run news48 feeds info 1
```
Expected: key-value pairs for feed details

### 2.8 Feeds info -- JSON output
```bash
uv run news48 feeds info 1 --json
```
Expected: `{"id": 1, "url": "...", "title": "...", ...}`

### 2.9 Feeds info -- not found
```bash
uv run news48 feeds info 99999 --json
```
Expected: `{"error": "Feed not found: 99999"}`, exit code 1

### 2.10 Feeds delete -- with confirmation (text)
```bash
uv run news48 feeds delete https://example.com/test-feed-2.xml
```
Expected: confirmation prompt, then deletion message

### 2.11 Feeds delete -- with --force
```bash
uv run news48 feeds delete https://example.com/test-feed.xml --force
```
Expected: `Deleted feed: ...`

### 2.12 Feeds delete -- JSON output
```bash
# Add a temporary feed first
uv run news48 feeds add https://example.com/temp.xml --json
uv run news48 feeds delete https://example.com/temp.xml --force --json
```
Expected: `{"deleted": true, "url": "...", "articles_removed": 0}`

### 2.13 Feeds update -- text output
```bash
uv run news48 feeds update 1 --title "Updated Feed Title"
```
Expected: `Updated feed: ...` with new title

### 2.14 Feeds update -- description only
```bash
uv run news48 feeds update 1 --description "New description"
```
Expected: `Updated feed: ...` with new description

### 2.15 Feeds update -- JSON output
```bash
uv run news48 feeds update 1 --title "Test" --json
```
Expected: `{"updated": true, "id": 1, "url": "...", "title": "Test", ...}`

### 2.16 Feeds update -- no fields specified
```bash
uv run news48 feeds update 1 --json
```
Expected: `{"error": "Must specify at least one of --title or --description"}`, exit code 1

### 2.17 Feeds update -- not found
```bash
uv run news48 feeds update 99999 --title "Test" --json
```
Expected: `{"error": "Feed not found: 99999"}`, exit code 1

---

## 3. Fetch

### 3.1 Fetch all -- text output
```bash
uv run news48 fetch
```
Expected: `Fetched N feeds, M entries, K valid` + success rate

### 3.2 Fetch all -- JSON output
```bash
uv run news48 fetch --json
```
Expected: `{"feed_filter": null, "feeds_fetched": N, ...}`

### 3.3 Fetch with --feed domain filter
```bash
uv run news48 fetch --feed arstechnica.com --json
```
Expected: `{"feed_filter": "arstechnica.com", "feeds_fetched": 1, ...}`

### 3.4 Fetch with --feed -- no match
```bash
uv run news48 fetch --feed nonexistent-domain.com --json
```
Expected: `{"feed_filter": "nonexistent-domain.com", "feeds_fetched": 0, ...}`

---

## 4. Articles List

### 4.1 Articles list -- text output
```bash
uv run news48 articles list
```
Expected: list of articles with status, title, URL

### 4.2 Articles list -- JSON output
```bash
uv run news48 articles list --json
```
Expected: `{"feed_filter": null, "status_filter": null, "total": N, ...}`

### 4.3 Articles list -- filter by status
```bash
uv run news48 articles list --status empty --json
```
Expected: only articles with status "empty"

### 4.4 Articles list -- filter by feed
```bash
uv run news48 articles list --feed arstechnica.com --json
```
Expected: only articles from arstechnica feeds

### 4.5 Articles list -- combined filters
```bash
uv run news48 articles list --feed bbc.com --status empty --limit 5 --json
```
Expected: up to 5 empty articles from bbc feeds

### 4.6 Articles list -- invalid status
```bash
uv run news48 articles list --status bogus --json
```
Expected: `{"error": "Invalid status 'bogus'. Valid: ..."}`, exit code 1

### 4.7 Articles list -- invalid status (text)
```bash
uv run news48 articles list --status bogus
```
Expected: `Error: Invalid status 'bogus'. Valid: ...` to stderr, exit code 1

---

## 5. Download

### 5.1 Download -- text output
```bash
uv run news48 download --limit 2
```
Expected: `Downloaded N of 2 articles, M failed`

### 5.2 Download -- JSON output
```bash
uv run news48 download --limit 2 --json
```
Expected: `{"feed_filter": null, "downloaded": N, "failed": M, "total": 2, "retry": false}`

### 5.3 Download with --feed
```bash
uv run news48 download --feed arstechnica.com --limit 3 --json
```
Expected: `{"feed_filter": "arstechnica.com", ...}`

### 5.4 Download --retry
```bash
uv run news48 download --retry --limit 5 --json
```
Expected: `{"retry": true, ...}` -- retries previously failed downloads

### 5.5 Download -- nothing to download
```bash
uv run news48 download --feed nonexistent-domain.com --json
```
Expected: `{"downloaded": 0, "failed": 0, "total": 0, ...}`

### 5.6 Download -- specific article
```bash
uv run news48 download --article 1
```
Expected: `Downloaded 1 of 1 articles, 0 failed` or error if article not found

### 5.7 Download -- specific article JSON
```bash
uv run news48 download --article 1 --json
```
Expected: `{"downloaded": 1, "failed": 0, "total": 1, ...}` or `{"error": "Article not found: 1"}`

---

## 6. Articles Info

### 6.1 Articles info -- text output
```bash
# Use an article ID from articles list
uv run news48 articles info 1
```
Expected: key-value pairs (ID, Title, URL, Status, Content length, etc.)

### 6.2 Articles info -- JSON output
```bash
uv run news48 articles info 1 --json
```
Expected: `{"id": 1, "content_length": N, "status": "...", ...}`
Verify: `content_length` is present but NOT the actual content

### 6.3 Articles info -- not found
```bash
uv run news48 articles info 99999 --json
```
Expected: `{"error": "Article not found: 99999"}`, exit code 1

---

## 7. Parse

Note: parse requires a configured LLM (API_BASE, MODEL in .env)

### 7.1 Parse -- text output
```bash
uv run news48 parse --limit 1
```
Expected: `Parsed N of 1 articles, M failed`

### 7.2 Parse -- JSON output
```bash
uv run news48 parse --limit 1 --json
```
Expected: `{"parsed": N, "failed": M, "total": 1, "retry": false, "results": [...]}`

### 7.3 Parse with --feed
```bash
uv run news48 parse --feed arstechnica.com --limit 2 --json
```
Expected: `{"feed_filter": "arstechnica.com", ...}`

### 7.4 Parse --retry
```bash
uv run news48 parse --retry --limit 5 --json
```
Expected: `{"retry": true, ...}` -- retries previously failed parses

### 7.5 Parse -- specific article
```bash
# Use an article ID that has been downloaded
uv run news48 parse --article 1 --json
```
Expected: `{"parsed": 1, ...}` or `{"error": "Article 1 has no content. Download it first."}`

---

## 8. Stats

### 8.1 Stats -- text output
```bash
uv run news48 stats
```
Expected: multi-line report with database size, article counts, feed info, runs

### 8.2 Stats -- JSON output
```bash
uv run news48 stats --json
```
Expected: `{"db_size_mb": N, "articles": {...}, "feeds": {...}, "runs": {...}}`

### 8.3 Stats with stale-days
```bash
uv run news48 stats --stale-days 1 --json
```
Expected: more feeds marked as stale

---

## 9. Fetches

### 9.1 Fetches list -- text output
```bash
uv run news48 fetches list
```
Expected: list of recent fetch runs with ID, status, timestamps, and counts

### 9.2 Fetches list -- JSON output
```bash
uv run news48 fetches list --json
```
Expected: `{"total": N, "limit": 20, "fetches": [...]}`

### 9.3 Fetches list -- with limit
```bash
uv run news48 fetches list --limit 5 --json
```
Expected: up to 5 fetch runs

---

## 10. Articles Delete

### 10.1 Articles delete -- with confirmation (text)
```bash
uv run news48 articles delete 1
```
Expected: confirmation prompt, then deletion message

### 10.2 Articles delete -- with --force
```bash
uv run news48 articles delete 1 --force
```
Expected: `Deleted article: ...`

### 10.3 Articles delete -- JSON output
```bash
uv run news48 articles delete 1 --force --json
```
Expected: `{"deleted": true, "id": 1, "url": "...", "title": "..."}`

### 10.4 Articles delete -- by URL
```bash
uv run news48 articles delete "https://example.com/article" --force --json
```
Expected: `{"deleted": true, ...}` or `{"deleted": false, "reason": "Article not found: ..."}`

### 10.5 Articles delete -- not found
```bash
uv run news48 articles delete 99999 --force --json
```
Expected: `{"deleted": false, "reason": "Article not found: 99999"}`, exit code 1

---

## 11. Articles Reset

### 11.1 Articles reset -- download flag
```bash
uv run news48 articles reset 1 --download
```
Expected: `Reset article: ...` with reset flags: download

### 11.2 Articles reset -- parse flag
```bash
uv run news48 articles reset 1 --parse
```
Expected: `Reset article: ...` with reset flags: parse

### 11.3 Articles reset -- all flags
```bash
uv run news48 articles reset 1 --all
```
Expected: `Reset article: ...` with reset flags: download, parse

### 11.4 Articles reset -- JSON output
```bash
uv run news48 articles reset 1 --all --json
```
Expected: `{"reset": true, "id": 1, "reset_download": true, "reset_parse": true}`

### 11.5 Articles reset -- no flags specified
```bash
uv run news48 articles reset 1 --json
```
Expected: `{"error": "Must specify --download, --parse, or --all"}`, exit code 1

### 11.6 Articles reset -- not found
```bash
uv run news48 articles reset 99999 --download --json
```
Expected: `{"error": "Article not found: 99999"}`, exit code 1

---

## 12. Articles Content

### 12.1 Articles content -- text output
```bash
uv run news48 articles content 1
```
Expected: article title, URL, content length, and full content

### 12.2 Articles content -- JSON output
```bash
uv run news48 articles content 1 --json
```
Expected: `{"id": 1, "title": "...", "url": "...", "content": "...", "content_length": N}`

### 12.3 Articles content -- no content
```bash
uv run news48 articles content 1
```
Expected: `(No content)` message if article has no downloaded content

### 12.4 Articles content -- not found
```bash
uv run news48 articles content 99999 --json
```
Expected: `{"error": "Article not found: 99999"}`, exit code 1

---

## 13. Logs

Note: logs commands require agent activity. Run agents first to generate logs.

### 13.1 Logs list -- text output
```bash
uv run news48 logs list
```
Expected: list of structured log entries with timestamp, module, message

### 13.2 Logs list -- JSON output
```bash
uv run news48 logs list --json
```
Expected: JSON array of log entries with timestamp, module, message, source_file

### 13.3 Logs list -- filter by agent
```bash
uv run news48 logs list --agent executor --json
uv run news48 logs list --agent planner --json
uv run news48 logs list --agent monitor --json
```
Expected: entries only from specified agent

### 13.4 Logs list -- filter by date
```bash
uv run news48 logs list --date today --json
uv run news48 logs list --date yesterday --json
uv run news48 logs list --date 2026-04-06 --json
```
Expected: entries only from specified date

### 13.5 Logs list -- filter by plan-id
```bash
uv run news48 logs list --plan-id plan-20260406-123456 --json
```
Expected: entries containing the plan ID in message or continuation

### 13.6 Logs list -- filter by module
```bash
uv run news48 logs list --module agents._run --json
```
Expected: entries from specified module

### 13.7 Logs list -- include prose
```bash
uv run news48 logs list --include-prose --json
```
Expected: includes free-form agent output lines

### 13.8 Logs list -- with limit and reverse
```bash
uv run news48 logs list --limit 10 --reverse --json
```
Expected: oldest 10 entries first

### 13.9 Logs list -- invalid agent
```bash
uv run news48 logs list --agent bogus --json
```
Expected: `{"error": "Invalid agent type 'bogus'. Choose from: executor, planner, monitor"}`, exit code 1

### 13.10 Logs list -- invalid date
```bash
uv run news48 logs list --date notadate --json
```
Expected: `{"error": "Invalid date 'notadate'. Use YYYY-MM-DD, 'today', or 'yesterday'."}`, exit code 1

### 13.11 Logs files -- text output
```bash
uv run news48 logs files
```
Expected: list of log files with size and modified date

### 13.12 Logs files -- JSON output
```bash
uv run news48 logs files --json
```
Expected: `[{"name": "...", "size": N, "modified": "..."}]`

### 13.13 Logs files -- filter by agent
```bash
uv run news48 logs files --agent executor --json
```
Expected: only executor log files

### 13.14 Logs files -- filter by date
```bash
uv run news48 logs files --date today --json
```
Expected: only log files from today

### 13.15 Logs show -- text output
```bash
uv run news48 logs show executor-20260406-025724
```
Expected: formatted log file content

### 13.16 Logs show -- JSON output
```bash
uv run news48 logs show executor-20260406-025724 --json
```
Expected: parsed log entries as JSON array

### 13.17 Logs show -- raw output
```bash
uv run news48 logs show executor-20260406-025724 --raw
```
Expected: raw log file content without formatting

### 13.18 Logs show -- not found
```bash
uv run news48 logs show nonexistent --json
```
Expected: `{"error": "Log file not found: nonexistent"}`, exit code 1

---

## 14. Error Handling

### 14.1 No database configured
```bash
DATABASE_PATH="" uv run news48 stats
```
Expected: `Error: DATABASE_PATH not configured` to stderr, exit code 1

### 14.2 Invalid database path
```bash
DATABASE_PATH=/nonexistent/path.db uv run news48 stats --json
```
Expected: `{"error": "..."}` to stdout, exit code 1

---

## 15. Lessons

### 15.1 Lessons list -- empty (no .lessons.md)
```bash
rm -f .lessons.md
uv run news48 lessons list
```
Expected: `No lessons found (.lessons.md does not exist).`

### 15.2 Lessons list -- JSON empty
```bash
uv run news48 lessons list --json
```
Expected: `{"lessons": [], "total": 0}`

### 15.3 Lessons add -- add a lesson
```bash
uv run news48 lessons add --agent executor --category "Command Syntax" --lesson "Use timeout=600 for fact-check" --json
```
Expected: `{"result": "Lesson saved for executor/Command Syntax: ...", "error": ""}`

### 15.4 Lessons add -- second lesson, different agent
```bash
uv run news48 lessons add --agent parser --category "Feed Quirks" --lesson "Some feeds use non-standard dates" --json
```
Expected: `{"result": "Lesson saved for parser/Feed Quirks: ...", "error": ""}`

### 15.5 Lessons list -- shows all lessons
```bash
uv run news48 lessons list
```
Expected: Human-readable grouped output with executor and parser sections.

### 15.6 Lessons list -- JSON with all lessons
```bash
uv run news48 lessons list --json
```
Expected: `{"lessons": [...], "total": 2}`

### 15.7 Lessons list -- filter by agent
```bash
uv run news48 lessons list --agent executor --json
```
Expected: Only executor lessons returned (total: 1).

### 15.8 Lessons list -- filter by category
```bash
uv run news48 lessons list --category "Feed" --json
```
Expected: Only "Feed Quirks" lessons returned (substring match).

### 15.9 Lessons add -- idempotent (duplicate skipped)
```bash
uv run news48 lessons add --agent executor --category "Command Syntax" --lesson "Use timeout=600 for fact-check" --json
```
Expected: `{"result": "Lesson already exists for executor/Command Syntax", "error": ""}`

### 15.10 Lessons add -- invalid agent
```bash
uv run news48 lessons add --agent badname --category "Test" --lesson "test" --json
```
Expected: `{"error": "Invalid agent 'badname'. Must be one of: ..."}`, exit code 1.

### 15.11 Cleanup
```bash
rm -f .lessons.md
```

---

## 16. Full Pipeline Walkthrough (stage by stage)

```bash
# 1. Start fresh
uv run news48 seed seed.txt --json

# 2. Check stats
uv run news48 stats --json

# 3. Fetch one feed
uv run news48 fetch --feed arstechnica.com --json

# 4. Check what needs downloading
uv run news48 articles list --feed arstechnica.com --status empty --json

# 5. Download articles
uv run news48 download --feed arstechnica.com --limit 3 --json

# 6. Check what needs parsing
uv run news48 articles list --feed arstechnica.com --status downloaded --json

# 7. Parse articles (requires LLM)
uv run news48 parse --feed arstechnica.com --limit 2 --json

# 8. Verify results
uv run news48 stats --json

# 9. Check for failures
uv run news48 articles list --status download-failed --json
uv run news48 articles list --status parse-failed --json

# 10. Retry failures
uv run news48 download --retry --json
uv run news48 parse --retry --json
```

---

## Cleanup

```bash
# Remove the test database
rm -f news48_test.db news48_test.db-wal news48_test.db-shm
```
