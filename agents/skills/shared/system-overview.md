# Skill: Understand the news48 system

## Scope
Always active — all agents must have a correct mental model of news48 before making decisions.

## What news48 Is

news48 is an **autonomous news ingestion and verification pipeline** run by four agents:

- **Planner** detects gaps in the work queue and creates plans.
- **Executor** executes one plan at a time, verifying each step.
- **Parser** claims downloaded articles and extracts structured data via LLM.
- **Monitor** evaluates health metrics and sends alerts.

---

## Data Model

news48 manages three core entities:

### Feeds
RSS/Atom subscription sources stored in the `feeds` table.
- Identity: `url`, `title`, `language`, `category`
- Freshness: `last_fetched_at` (updated after each fetch run)
- Feeds start in `never_fetched` state and move to `stale` after the configured threshold.

### Fetches
One row per fetch run in the `fetches` table — aggregate record of what happened.
- Fields: `started_at`, `completed_at`, `status`, `feeds_fetched`, `articles_found`
- **Not a per-feed record** — do not use `fetches.articles_found` to prove per-feed article insertion.

### Articles
Individual news articles in the `articles` table.
- Derived statuses (not a single column): `empty` → `downloaded` → `parsed` → `fact-checked`
- Failure states: `download-failed`, `parse-failed`, `fact-unchecked`
- Processing concurrency: `processing_status`, `processing_owner`, `processing_started_at`

---

## Pipeline Stages

```
seed → fetch → download → parse → cleanup
```

| Stage | What it does | Failure state |
|-------|-------------|---------------|
| **seed** | Insert feed URLs from a text file into the database | none |
| **fetch** | Read RSS/Atom feeds, insert article metadata | fetch-failed feeds |
| **download** | Fetch full HTML for articles via bypass proxy | download-failed |
| **parse** | Extract structured data from HTML via LLM | parse-failed |
| **cleanup** | Delete articles older than retention window | — |

**Important**: Each stage is idempotent. Running fetch twice merges new entries; running download twice skips already-downloaded articles.

---

## Plans and the Plan Queue

Plans have this structure:
- `id`: unique plan identifier
- `task`: overall goal description
- `steps`: ordered list of `{id, description, status, result}`
- `success_conditions`: outcome criteria for verification
- `parent_id`: for sequential dependencies (e.g., download depends on fetch)
- `requeue_count`: incremented when executor reclaims a stuck plan

**Active plans** are those with status `pending` or `executing`. Planner must check existing active plans before creating new ones to avoid duplication.

---

## Backlog Derived States

Do not assume a single canonical status column exists. Article state is derived:

| CLI status | Meaning |
|-----------|---------|
| `empty` | article row exists, no HTML content yet |
| `downloaded` | HTML content is stored |
| `parsed` | LLM extraction complete, structured fields populated |
| `download-failed` | bypass/byparr could not retrieve content |
| `parse-failed` | LLM parsing returned an error |
| `fact-unchecked` | parsed but not yet fact-checked |
| `fact-checked` | verdict and supporting evidence stored |

Concurrency states (set during active processing):
- `processing_status`: `claimed`, `completed`, `failed`
- `processing_owner`: which agent/thread claimed it
- `processing_started_at`: when the claim was taken

---

## Accepted Status Values

### Plan statuses
- `pending` — waiting to be claimed
- `executing` — actively running under a claimed executor
- `completed` — all steps finished successfully (terminal)
- `failed` — steps did not succeed or plan was cancelled (terminal)

### Fetch run statuses
- `running` — fetch is in progress
- `completed` — fetch finished successfully
- `failed` — fetch finished with errors

### Article processing statuses
- `claimed` — article is being processed by an agent

### Article derived statuses (CLI `--status` filter values)
- `empty` — row exists, no HTML content yet
- `downloaded` — HTML stored, not yet parsed
- `parsed` — LLM extraction done
- `download-failed` — bypass/byparr could not retrieve content
- `parse-failed` — LLM parsing error
- `fact-unchecked` — parsed but no fact-check verdict yet
- `fact-checked` — fact-check verdict is stored

### Fact-check verdict statuses
- `verified` — claims in the article are accurate
- `disputed` — claims are inaccurate or misleading
- `unverifiable` — cannot verify claims
- `mixed` — article contains both accurate and inaccurate claims

---

## Forbidden Mental Models

- ~~"articles have a status column"~~ — status is derived from multiple fields
- ~~"fetches table tracks per-feed results"~~ — it tracks aggregate run outcomes only
- ~~"all feeds are always reachable"~~ — some feeds are permanently or temporarily unreachable
- ~~"parsing means the article is fact-check eligible"~~ — fact-check has separate eligibility rules
- ~~"a plan can be created for anything"~~ — plans must represent meaningful work that changes or unblocks state