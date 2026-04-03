# News48 Workflow Guide

This guide explains the end-to-end workflow for using the `news48` CLI to fetch, download, and parse news articles, including autonomous agents for pipeline execution, monitoring, and reporting.

## Overview

The news48 pipeline consists of five main stages:

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   1. Seed   │───▶│  2. Fetch   │───▶│  3. Download │───▶│   4. Parse  │───▶│ 5. Maintain │
│  (Feeds)    │    │  (Articles) │    │  (Content)   │    │  (Analysis) │    │ (Autonomous)│
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
```

---

## Stage 1: Seed the Database

Before you can fetch articles, you need to add RSS/Atom feed URLs to the database.

### Create a Seed File

Create a text file with one feed URL per line:

```bash
# newsfeeds.seed.txt
https://feeds.arstechnica.com/arstechnica/index
https://feeds.bbci.co.uk/news/rss.xml
https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml
```

### Run the Seed Command

```bash
# Add feeds from the seed file
uv run news48 seed newsfeeds.seed.txt

# Output: Seeded 3 new feeds (0 skipped, 3 total)
```

### Verify Feeds Were Added

```bash
# List all feeds (default: 20 per page)
uv run news48 feeds list

# Paginate feeds
uv run news48 feeds list --limit 50 --offset 20

# Get detailed info about a specific feed
uv run news48 feeds info 1
```

### Add Individual Feeds

You can also add feeds one at a time:

```bash
# Add a single feed
uv run news48 feeds add https://example.com/feed.xml

# Add with JSON output for scripting
uv run news48 feeds add https://example.com/feed.xml --json
```

---

## Stage 2: Fetch Articles

Once feeds are seeded, fetch article metadata from those feeds.

### Fetch All Feeds

```bash
# Fetch all feeds
uv run news48 fetch

# Output: Fetched 3 feeds, 45 entries, 42 valid
#         Success rate: 100.0%
```

### Fetch Specific Feeds

```bash
# Fetch only feeds from a specific domain
uv run news48 fetch --feed arstechnica.com

# Fetch with custom delay between requests
uv run news48 fetch --delay 2.0
```

### Check Fetch Results

```bash
# View fetch history
uv run news48 fetches list

# Check article counts
uv run news48 stats
```

### What Happens During Fetch

1. The CLI reads all feed URLs from the database
2. For each feed, it downloads the RSS/Atom XML
3. It parses the feed and extracts article metadata (title, URL, summary, author, date)
4. New articles are inserted into the database
5. Feed metadata (title, description) is updated

---

## Stage 3: Download Article Content

After fetching, articles only have metadata. Download the full HTML content for parsing.

### Check What Needs Downloading

```bash
# List articles with no content (default: 20 per page)
uv run news48 articles list --status empty

# Paginate articles
uv run news48 articles list --status empty --limit 50 --offset 20

# Count articles needing download
uv run news48 articles list --status empty --json | jq '.total'
```

### Download Articles

```bash
# Download up to 10 articles
uv run news48 download --limit 10

# Download articles from a specific feed
uv run news48 download --feed arstechnica.com --limit 5

# Download with custom delay between requests
uv run news48 download --limit 10 --delay 2.0

# Download a specific article by ID
uv run news48 download --article 42
```

### Download with Retry

```bash
# Retry failed downloads
uv run news48 download --retry --limit 20
```

### Check Download Status

```bash
# List downloaded articles
uv run news48 articles list --status downloaded

# Check for download failures
uv run news48 articles list --status download-failed
```

### What Happens During Download

1. The CLI identifies articles without content
2. For each article, it fetches the full HTML page
3. It uses bypass techniques to handle anti-bot protections
4. The HTML content is stored in the database
5. Failed downloads are marked with error messages

---

## Stage 4: Parse Articles with LLM

The final stage uses an LLM to extract structured data from the HTML content.

### Prerequisites

Parsing requires a configured LLM and database. Set these in your `.env` file:

```bash
# Required for all commands
DATABASE_PATH=news48.db
BYPARR_API_URL=http://localhost:8000

# Required for parsing (LLM configuration)
API_BASE=https://api.openai.com/v1
MODEL=gpt-4
API_KEY=your-api-key-here
CONTEXT_WINDOW=131072
```

### Check What Needs Parsing

```bash
# List articles with content but not yet parsed
uv run news48 articles list --status downloaded

# Count articles needing parsing
uv run news48 articles list --status downloaded --json | jq '.total'
```

### Parse Articles

```bash
# Parse up to 5 articles
uv run news48 parse --limit 5

# Parse articles from a specific feed
uv run news48 parse --feed arstechnica.com --limit 3

# Parse with custom delay between operations
uv run news48 parse --limit 5 --delay 2.0

# Parse a specific article by ID
uv run news48 parse --article 42
```

### Parse with Retry

```bash
# Retry failed parses
uv run news48 parse --retry --limit 10
```

### Check Parse Results

```bash
# List parsed articles
uv run news48 articles list --status parsed

# View parsed article details
uv run news48 articles info 42

# View article content
uv run news48 articles content 42

# Check for parse failures
uv run news48 articles list --status parse-failed
```

### What Happens During Parse

1. The CLI identifies articles with content but no parse results
2. For each article, it creates a temporary file with the HTML
3. The LLM agent analyzes the HTML and extracts:
   - Improved title (factual, non-clickbait)
   - Full article content
   - Publication date
   - Sentiment (positive/negative/neutral)
   - Categories (e.g., technology, politics)
   - Tags (e.g., specific keywords)
   - Countries mentioned
   - Brief summary
4. The parsed data is stored in the database
5. The temporary HTML file is deleted

---

## Complete Workflow Example

Here's a complete end-to-end workflow:

```bash
# 1. Start fresh (optional - skip if database already has data)
rm -f news48.db

# 2. Seed the database with feeds
uv run news48 seed newsfeeds.seed.txt

# 3. Check initial stats
uv run news48 stats

# 4. Fetch articles from all feeds
uv run news48 fetch

# 5. Download content for first 10 articles
uv run news48 download --limit 10

# 6. Parse the downloaded articles
uv run news48 parse --limit 10

# 7. View final statistics
uv run news48 stats

# 8. Browse parsed articles
uv run news48 articles list --status parsed
```

---

## Monitoring and Maintenance

### Check System Health

```bash
# View comprehensive statistics
uv run news48 stats

# View stats with custom stale threshold (default: 7 days)
uv run news48 stats --stale-days 14

# Check pipeline backlogs
uv run news48 stats --json | jq '.articles.download_backlog, .articles.parse_backlog'
```

### Handle Failures

```bash
# List failed downloads
uv run news48 articles list --status download-failed

# Retry all failed downloads
uv run news48 download --retry

# List failed parses
uv run news48 articles list --status parse-failed

# Retry all failed parses
uv run news48 parse --retry
```

### Reset Articles for Re-processing

```bash
# Reset download failure flag
uv run news48 articles reset 42 --download

# Reset parse failure flag
uv run news48 articles reset 42 --parse

# Reset both flags
uv run news48 articles reset 42 --all
```

### Manage Feeds

```bash
# Add a new feed
uv run news48 feeds add https://example.com/new-feed.xml

# Update feed metadata
uv run news48 feeds update 1 --title "New Title"

# Delete a feed and its articles
uv run news48 feeds delete 1 --force

# View feed details
uv run news48 feeds info 1
```

### Manage Articles

```bash
# Delete a specific article
uv run news48 articles delete 42 --force

# View article details
uv run news48 articles info 42

# View article content
uv run news48 articles content 42
```

---

## JSON Output for Automation

All commands support `--json` output for scripting:

```bash
# Get total article count
uv run news48 articles list --json | jq '.total'

# Get parsed article count
uv run news48 articles list --status parsed --json | jq '.total'

# Get feed list as JSON
uv run news48 feeds list --json

# Get statistics as JSON
uv run news48 stats --json
```

---

## Tips and Best Practices

1. **Start Small**: Begin with a few feeds and small limits (5-10 articles) to test
2. **Monitor Failures**: Regularly check for download and parse failures
3. **Use Retry**: The `--retry` flag is your friend for handling transient errors
4. **Filter by Feed**: Use `--feed` to focus on specific sources
5. **Check Stats**: Use `stats` command to monitor pipeline health
6. **JSON for Scripts**: Use `--json` output for automation and monitoring scripts
7. **Rate Limiting**: Use `--delay` to avoid overwhelming servers
8. **Batch Processing**: Process articles in batches rather than all at once

---

## Troubleshooting

### No Feeds Found

```bash
# Check if feeds are seeded
uv run news48 feeds list

# Add feeds if empty
uv run news48 seed newsfeeds.seed.txt
```

### No Articles to Download

```bash
# Check if fetch has been run
uv run news48 fetches list

# Run fetch if needed
uv run news48 fetch
```

### Download Failures

```bash
# Check failure reasons
uv run news48 articles list --status download-failed --json

# Reset and retry
uv run news48 articles reset 42 --download
uv run news48 download --article 42
```

### Parse Failures

```bash
# Check failure reasons
uv run news48 articles list --status parse-failed --json

# Verify LLM configuration
cat .env | grep -E "API_BASE|MODEL|API_KEY"

# Reset and retry
uv run news48 articles reset 42 --parse
uv run news48 parse --article 42
```

---

## Stage 5: Agent-Based Management

The news48 system uses LlamaIndex `FunctionAgent` instances for autonomous pipeline execution, monitoring, and reporting. All agents share a consistent interface: `get_agent()` returns the configured agent, and `run(task)` executes it with a task prompt.

### Check Agent Status

```bash
# Show status of all agents (schedule, last run, next run)
uv run news48 agents status

# JSON output
uv run news48 agents status --json
```

### Run Agents

```bash
# Run all due agents (based on schedule)
uv run news48 agents run

# Run specific agent
uv run news48 agents run --agent pipeline
uv run news48 agents run --agent monitor
uv run news48 agents run --agent reporter
uv run news48 agents run --agent checker

# Run agent with custom task prompt
uv run news48 agents run --agent pipeline --task "Fetch bbc.co.uk feeds and download 5 articles"
uv run news48 agents run --agent checker --task "Fact-check articles about politics from the last 24 hours"

# JSON output
uv run news48 agents run --agent monitor --json
```

### Generate Reports

```bash
# Daily report
uv run news48 agents report --type daily

# Weekly report as JSON
uv run news48 agents report --type weekly --json

# Monthly report
uv run news48 agents report --type monthly
```

### What Each Agent Does

#### Pipeline Agent
- Runs the full news48 pipeline: fetch, download, parse, cleanup
- Executes stages one at a time, inspects results between stages
- Handles failures with retries
- Enforces 48-hour retention policy (absorbs former Maintainer duties)

#### Monitor Agent
- Intelligent system health observation with LLM reasoning
- Gathers metrics via CLI, reasons about patterns and anomalies
- Generates alerts with severity classification (info/warning/critical)
- Suggests concrete corrective actions
- Read-only (no side effects)

#### Reporter Agent
- Generates natural language reports (daily/weekly/monthly)
- Analyzes pipeline performance with concrete metrics
- Tracks retention compliance
- Provides trend analysis and executive-style summaries

#### Checker Agent (Fact Checker)
- Selectively verifies parsed articles by searching for independent sources
- Focuses on high-impact categories: politics, health, science, conflict
- Extracts key claims and searches for corroborating or contradicting evidence
- Records verdicts in the database: `verified`, `disputed`, `unverifiable`, `mixed`
- Uses web search (`perform_web_search`) and page fetching (`fetch_webpage_content`)

### Agent Architecture

```
                    Orchestrator
              (Python dispatcher, NOT an LLM agent)
              Runs agents on a schedule
                         |
         ┌───────────┬───┴───┬───────────┐
         |           |       |           |
         v           v       v           v
  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
  | Pipeline | | Monitor  | | Reporter | | Checker  |
  | (Worker) | |(Observer)| |(Summary) | |(Verifier)|
  └──────────┘ └──────────┘ └──────────┘ └──────────┘
         |           |       |           |
         v           v       v           v
  ┌──────────────────────────────────────────────────┐
  │             Shared Tool Library                   │
  │  shell / files / planner / search / bypass / sys  │
  └──────────────────────────────────────────────────┘
```

All agents are LlamaIndex `FunctionAgent` instances except the Orchestrator, which is a pure Python dispatcher. The Orchestrator does not use an LLM -- it simply runs agents on a timer with predefined task prompts.

### Scheduled Maintenance

The orchestrator runs agents on a schedule:

- **Pipeline**: Every 60 minutes
- **Monitor**: Every 15 minutes
- **Reporter**: Every 24 hours (daily)
- **Checker**: Every 6 hours

> **Note**: Agent schedules are currently configured in code. A future
> enhancement will add persistent schedule management via CLI commands.

### Manual CLI vs Autonomous Agent Operations

| Operation | Manual CLI Command | Autonomous Agent |
|-----------|-------------------|------------------|
| Run full pipeline | `uv run news48 fetch && download && parse` | Pipeline Agent (every 60 min) |
| Purge old articles | `uv run news48 cleanup purge --force` | Pipeline Agent (end of cycle) |
| Check database health | `uv run news48 cleanup health` | Monitor Agent (every 15 min) |
| View retention status | `uv run news48 cleanup status` | Monitor Agent (alerts) |
| View system stats | `uv run news48 stats` | Reporter Agent (daily reports) |
| Generate reports | Manual via `uv run news48 stats` | Reporter Agent (scheduled) |
| Fact-check an article | `uv run news48 articles check <id> --status verified` | Checker Agent (every 6 hours) |
| List fact-checked articles | `uv run news48 articles list --status fact-checked` | Checker Agent (automatic) |

**Key Principle**: Use Manual CLI for one-off operations and troubleshooting. Use Autonomous Agents for scheduled, recurring maintenance.

---

## Complete Pipeline with Maintenance

```bash
# 1. Start fresh (optional)
rm -f news48.db

# 2. Seed the database with feeds
uv run news48 seed newsfeeds.seed.txt

# 3. Check initial stats
uv run news48 stats

# 4. Fetch articles from all feeds
uv run news48 fetch

# 5. Download content for first 10 articles
uv run news48 download --limit 10

# 6. Parse the downloaded articles
uv run news48 parse --limit 10

# 7. View final statistics
uv run news48 stats

# 8. Check retention policy status
uv run news48 cleanup status

# 9. Run maintenance (purge expired articles)
uv run news48 cleanup purge --force

# 9b. Preview what would be purged (dry run)
uv run news48 cleanup purge --dry-run

# 10. Verify database health
uv run news48 cleanup health
```

Or run the entire pipeline autonomously:

```bash
# Run the Pipeline Agent
uv run news48 agents run --agent pipeline

# Or let the Orchestrator handle it on schedule
uv run news48 agents run
```

---

## Next Steps

- See [CLI Testing Guide](cli-testing-guide.md) for detailed command reference
- Check [README.md](../README.md) for installation and configuration
- Review [pyproject.toml](../pyproject.toml) for project dependencies
- See [Pipeline Agent Instructions](../agents/instructions/pipeline.md) for pipeline details
- See [Monitor Agent Instructions](../agents/instructions/monitor.md) for monitoring details
- See [Reporter Agent Instructions](../agents/instructions/reporter.md) for reporting details
- See [Checker Agent Instructions](../agents/instructions/checker.md) for fact-checking details
