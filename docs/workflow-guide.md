# News48 Workflow Guide

This guide explains the end-to-end workflow for using the `news48` CLI to fetch, download, parse, and fact-check news articles, including autonomous agents for pipeline execution and health monitoring.

## Overview

The system has two related workflows:

1. **Setup**: seed feeds into the database when onboarding or changing sources
2. **Recurring pipeline cycle**: fetch → download → parse → fact-check → cleanup

Scheduled agents and the orchestrator sit above that recurring cycle; they are not a separate pipeline stage.

```
Setup: seed feeds

Recurring cycle:
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│    Fetch    │───▶│  Download   │───▶│    Parse    │───▶│ Fact-check  │───▶│   Cleanup   │
│ (metadata)  │    │   (HTML)    │    │ (analysis)  │    │ (verdict)   │    │ (retention) │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘

Scheduled agents (orchestrator):
┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
│ Sentinel │  │ Executor │  │  Parser  │  │Fact-check│
│(Health)  │  │ (Plans)  │  │(Articles)│  │(Articles)│
└──────────┘  └──────────┘  └──────────┘  └──────────┘
```

---

## Stage 1: Seed the Database

Before you can fetch articles, you need to add RSS/Atom feed URLs to the database.

### Create a Seed File

Create a text file with one feed URL per line:

```bash
# seed.txt
https://feeds.arstechnica.com/arstechnica/index
https://feeds.bbci.co.uk/news/rss.xml
https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml
```

### Run the Seed Command

```bash
# Add feeds from the seed file
uv run news48 seed seed.txt

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

### Generate Feed RSS

```bash
# Generate RSS feed from saved articles
uv run news48 feeds rss --feed arstechnica.com

# Generate RSS for a specific date range
uv run news48 feeds rss --feed arstechnica.com --days 7
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

The next stage uses an LLM to extract structured data from the HTML content.

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

## Stage 5: Fact-Check Articles

The fact-check stage searches for evidence and records verdicts on article claims.

### Check What Needs Fact-Checking

```bash
# List articles that haven't been fact-checked
uv run news48 articles list --status parsed

# Count fact-checkable articles
uv run news48 articles list --status parsed --json | jq '.total'
```

### Run Fact-Check

```bash
# Fact-check up to 10 articles
uv run news48 fact-check

# Fact-check with custom limit
uv run news48 fact-check --limit 5

# Fact-check with JSON output for scripting
uv run news48 fact-check --json
```

### Check Fact-Check Results

```bash
# List fact-checked articles
uv run news48 articles list --status fact-checked

# View article with fact-check verdict
uv run news48 articles info 42

# List articles with failed fact-check attempts
uv run news48 articles list --status fact-check-failed
```

### What Happens During Fact-Check

1. The CLI identifies articles that are parsed but not yet fact-checked
2. For each article, it extracts claims from the parsed content
3. It searches the web for evidence using SearXNG
4. It evaluates the claims against the evidence
5. It records a verdict (verified, false, unverified, or mixed) for each article

---

## Stage 6: Cleanup and Retention

The cleanup stage removes old articles based on retention policy.

### Check Retention Status

```bash
# View retention policy status
uv run news48 cleanup status

# View cleanup history
uv run news48 cleanup history
```

### Purge Old Articles

```bash
# Preview what would be purged (dry run)
uv run news48 cleanup purge --dry-run

# Purge expired articles
uv run news48 cleanup purge --force
```

### Database Health

```bash
# Check database health
uv run news48 cleanup health
```

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

# 7. Fact-check parsed articles
uv run news48 fact-check --limit 5

# 8. View final statistics
uv run news48 stats

# 9. Check retention policy status
uv run news48 cleanup status

# 10. Browse parsed articles
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

# List failed fact-checks
uv run news48 articles list --status fact-check-failed
```

### Reset Articles for Re-processing

```bash
# Reset download failure flag
uv run news48 articles reset 42 --download

# Reset parse failure flag
uv run news48 articles reset 42 --parse

# Reset fact-check status
uv run news48 articles reset 42 --fact-check

# Reset all flags
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

# Generate RSS for a feed
uv run news48 feeds rss --feed arstechnica.com
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

### Search Articles

```bash
# Search article content
uv run news48 search "climate change"

# Search with custom limit
uv run news48 search "technology" --limit 20
```

### Generate Sitemap

```bash
# Generate XML sitemap from parsed articles
uv run news48 sitemap --output sitemap.xml

# Generate sitemap with custom URL base
uv run news48 sitemap --url https://example.com --output sitemap.xml
```

---

## Log Inspection

The `logs` command group provides structured access to agent execution logs stored in `data/logs/`:

### List Log Entries

```bash
# List recent log entries from all agents
uv run news48 logs list

# Filter by agent type
uv run news48 logs list --agent executor
uv run news48 logs list --agent sentinel
uv run news48 logs list --agent fact_checker
uv run news48 logs list --agent parser

# Filter by date
uv run news48 logs list --date today
uv run news48 logs list --date yesterday
uv run news48 logs list --date 2026-04-06

# Filter by plan ID (for debugging specific plans)
uv run news48 logs list --plan-id plan-20260406-123456

# Filter by module name
uv run news48 logs list --module agents._run

# Include free-form agent output (prose)
uv run news48 logs list --include-prose

# JSON output for scripting
uv run news48 logs list --agent executor --json

# Control output order and limit
uv run news48 logs list --limit 50 --reverse
```

### Discover Log Files

```bash
# List available log files with metadata
uv run news48 logs files

# Filter by agent
uv run news48 logs files --agent executor

# Filter by date
uv run news48 logs files --date today

# JSON output
uv run news48 logs files --json
```

### View Full Log File

```bash
# Display a log file (accepts stem or full name)
uv run news48 logs show executor-20260406-025724
uv run news48 logs show executor-20260406-025724.log

# Raw output (no formatting)
uv run news48 logs show executor-20260406-025724 --raw

# JSON output (parsed entries)
uv run news48 logs show executor-20260406-025724 --json
```

### When to Use Logs

- **Debug failures**: Investigate download or parse failures by reviewing executor logs
- **Track plan execution**: Follow a specific plan's progress with `--plan-id`
- **Monitor agent activity**: Review recent agent sessions for patterns or anomalies
- **Correlate errors**: Match log timestamps with error spikes in stats

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

# Review executor logs for error patterns
uv run news48 logs list --agent executor --module httpx --json

# Reset and retry
uv run news48 articles reset 42 --download
uv run news48 download --article 42
```

### Parse Failures

```bash
# Check failure reasons
uv run news48 articles list --status parse-failed --json

# Review executor logs for LLM errors
uv run news48 logs list --agent executor --module agents._run --json

# Verify LLM configuration
cat .env | grep -E "API_BASE|MODEL|API_KEY"

# Reset and retry
uv run news48 articles reset 42 --parse
uv run news48 parse --article 42
```

### Plan Execution Issues

```bash
# Check for stuck executing plans
uv run news48 plans list --status executing --json

# Review executor logs for a specific plan
uv run news48 logs list --plan-id plan-20260406-123456 --json

# Check recent executor activity
uv run news48 logs list --agent executor --limit 20 --json
```

---

## Scheduled Agents and the Orchestrator

The news48 system runs four autonomous agents on a schedule managed by the Orchestrator. The Orchestrator is a pure Python dispatcher — it is not an LLM agent itself.

### Valid Agent Names

The four active runtime agents are:

| Agent | Purpose | Schedule |
|-------|---------|----------|
| `sentinel` | Health monitoring, threshold evaluation, feed curation | Every 5 minutes |
| `executor` | Claims and executes plans from the queue | Every 1 minute (up to 5 concurrent) |
| `parser` | Claims and parses downloaded articles from the database | Every 1 minute (up to 5 concurrent) |
| `fact_checker` | Claims and fact-checks parsed articles | Every 5 minutes (up to 3 concurrent) |

### Check Agent Status

```bash
# Show status of all agents (schedule, last run, next run)
uv run news48 agents status

# JSON output
uv run news48 agents status --json
```

### Run Agents Manually

```bash
# Run all due agents (based on schedule)
uv run news48 agents run

# Run specific agent
uv run news48 agents run --agent sentinel
uv run news48 agents run --agent executor
uv run news48 agents run --agent parser
uv run news48 agents run --agent fact_checker

# Run agent with custom task prompt
uv run news48 agents run --agent sentinel --task "Run a health check cycle"
uv run news48 agents run --agent fact_checker --task "Run a fact-check cycle for technology articles"

# JSON output
uv run news48 agents run --agent fact_checker --json
```

### What Each Agent Does

#### Sentinel Agent
- Runs health monitoring cycles every 5 minutes
- Gathers system health metrics via CLI commands
- Evaluates thresholds and detects issues
- Creates fix plans for consistently problematic feeds
- Writes structured reports to `data/monitor/latest-report.json`

#### Executor Agent
- Claims one eligible pending plan and executes its steps
- Runs plan work and final verification without creating plans
- Performs final verification against plan success conditions
- Marks each plan completed or failed with evidence
- Does not create plans — only executes them

#### Parser Agent
- Runs on its own schedule, independent of plan files
- Claims eligible downloaded articles directly from the database
- Parses one claimed article at a time
- Updates the article record and releases the claim when done
- Prevents duplicate parse work across concurrent parser processes

#### Fact-Checker Agent
- Runs on its own schedule, independent of plan files
- Claims fact-unchecked articles directly from the database
- Searches for evidence using SearXNG
- Records verdicts (verified, false, unverified, mixed)
- Prevents duplicate fact-check work across concurrent processes

### Agent Architecture

```
                    Orchestrator
              (Python dispatcher, NOT an LLM agent)
              Runs agents on a schedule
                         |
        ┌────────────┬───────────┬──────────┬──────────────┐
        |            |           |          |              |
        v            v           v          v              v
 ┌──────────┐  ┌──────────┐ ┌──────────┐ ┌─────────────┐
 │ Sentinel │  │ Executor │ │  Parser  │ │Fact-checker │
 │(Health)  │  │ (Plans)  │ │(Articles)│  │ (Articles)  │
 └──────────┘  └──────────┘ └──────────┘ └─────────────┘
       |             |           |              |
       v             v           v              v
 ┌──────────────────────────────────────────────────────┐
 │             Shared Tool Library                       │
 │  shell / files / planner / searxng / bypass / system  │
 └──────────────────────────────────────────────────────┘
```

### Manual CLI vs Autonomous Agent Operations

| Operation | Manual CLI Command | Autonomous Agent |
|-----------|-------------------|------------------|
| Run recurring pipeline cycle | `uv run news48 fetch && uv run news48 download --limit 10 && uv run news48 parse --limit 10` | Sentinel → Executor → Parser loop |
| Fact-check articles | `uv run news48 fact-check` | Fact-checker agent on schedule |
| Check database health | `uv run news48 cleanup health` | Sentinel Agent (every 5m) |
| View retention status | `uv run news48 cleanup status` | Sentinel Agent (alerts) |
| View system stats | `uv run news48 stats` | Sentinel Agent report context |
| Purge old articles | `uv run news48 cleanup purge --force` | Executor via explicit cleanup plan steps |

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

# 7. Fact-check parsed articles
uv run news48 fact-check --limit 5

# 8. View final statistics
uv run news48 stats

# 9. Check retention policy status
uv run news48 cleanup status

# 10. Run maintenance (purge expired articles)
uv run news48 cleanup purge --force

# 10b. Preview what would be purged (dry run)
uv run news48 cleanup purge --dry-run

# 11. Verify database health
uv run news48 cleanup health
```

Or run the agent system autonomously:

```bash
# Run specific agents explicitly
uv run news48 agents run --agent sentinel
uv run news48 agents run --agent executor
uv run news48 agents run --agent parser
uv run news48 agents run --agent fact_checker

# Or let the Orchestrator handle it on schedule
uv run news48 agents run
```

---

## Next Steps

- See [CLI Testing Guide](cli-testing-guide.md) for detailed command reference
- Check [README.md](../README.md) for installation and configuration
- Review [pyproject.toml](../pyproject.toml) for project dependencies
- See [Sentinel Agent Instructions](../agents/instructions/sentinel.md) for health monitoring details
- See [Executor Agent Instructions](../agents/instructions/executor.md) for plan execution details
- See [Parser Agent Instructions](../agents/instructions/parser.md) for parsing details
- See [Fact-checker Agent Instructions](../agents/instructions/fact_checker.md) for fact-checking details
