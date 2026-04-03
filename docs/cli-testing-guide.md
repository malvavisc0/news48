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
uv run news48 seed newsfeeds.seed.txt
```
Expected: `Seeded N new feeds (M skipped, 55 total)`

### 1.2 Seed -- JSON output
```bash
uv run news48 seed newsfeeds.seed.txt --json
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

## 9. Error Handling

### 9.1 No database configured
```bash
DATABASE_PATH="" uv run news48 stats
```
Expected: `Error: DATABASE_PATH not configured` to stderr, exit code 1

### 9.2 Invalid database path
```bash
DATABASE_PATH=/nonexistent/path.db uv run news48 stats --json
```
Expected: `{"error": "..."}` to stdout, exit code 1

---

## 10. Full Pipeline Walkthrough (stage by stage)

```bash
# 1. Start fresh
uv run news48 seed newsfeeds.seed.txt --json

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
