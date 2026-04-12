# News48 Workflow Guide

This guide explains the end-to-end workflow for using the `news48` CLI to fetch, download, and parse news articles, including autonomous agents for pipeline execution, monitoring, and reporting.

## Overview

The system has two related workflows:

1. **Setup**: seed feeds into the database when onboarding or changing sources
2. **Recurring pipeline cycle**: fetch -> download -> parse -> cleanup

Autonomous agents and the orchestrator sit above that recurring cycle; they are not a separate pipeline stage.

```
Setup: seed feeds

Recurring cycle:
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│    Fetch    │───▶│  Download   │───▶│    Parse    │───▶│   Cleanup   │
│ (metadata)  │    │   (HTML)    │    │ (analysis)  │    │ (retention) │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
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

## Log Inspection

The `logs` command group provides structured access to agent execution logs stored in `.logs/`:

### List Log Entries

```bash
# List recent log entries from all agents
uv run news48 logs list

# Filter by agent type
uv run news48 logs list --agent executor
uv run news48 logs list --agent planner
uv run news48 logs list --agent monitor

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

## Autonomous Agents and Scheduling

The news48 system uses LlamaIndex `FunctionAgent` instances for autonomous planning, execution, parsing, and monitoring. All agents share a consistent interface: `get_agent()` returns the configured agent, and the runtime invokes the appropriate run entrypoint for the agent's mode.

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
uv run news48 agents run --agent planner
uv run news48 agents run --agent executor
uv run news48 agents run --agent parser
uv run news48 agents run --agent monitor

# Run agent with custom task prompt
uv run news48 agents run --agent planner --task "Run a full planning cycle and ensure fact-check coverage goals are planned"
uv run news48 agents run --agent executor --task "Claim and execute one pending plan with verification"

# JSON output
uv run news48 agents run --agent monitor --json
```

### What Each Agent Does

#### Planner Agent
- Gathers evidence from CLI metrics and current plan state
- Detects unmet goals across pipeline flow, retries, fact-check coverage, and health
- Creates minimum plans with explicit success conditions
- Avoids duplicate work already covered by pending or executing plans

#### Executor Agent
- Claims one eligible pending plan and executes steps in order
- Runs plan work and final verification without creating plans
- Performs final verification against plan success conditions
- Marks each plan completed or failed with evidence

#### Parser Agent
- Runs on its own schedule and does not consume plan files
- Claims eligible downloaded articles directly from the database
- Parses one claimed article at a time from the standard parser task payload
- Updates the article record and releases the claim when done
- Prevents duplicate parse work across concurrent parser processes

#### Monitor Agent
- Intelligent system health observation with LLM reasoning
- Gathers metrics via CLI, reasons about patterns and anomalies
- Generates alerts with severity classification (info/warning/critical)
- Suggests concrete corrective actions
- Read-only except optional email delivery when configured

Fact-checking is executed by the Executor when the Planner creates fact-check plans. It is not a separate scheduled agent in the current architecture.

### Agent Architecture

```
                    Orchestrator
              (Python dispatcher, NOT an LLM agent)
              Runs agents on a schedule
                         |
         ┌───────────┬──────────┬──────────┬───────────┐
         |           |          |          |
         v           v          v          v
  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
  | Planner  | | Executor | |  Parser  | | Monitor  |
  | (Plans)  | | (Worker) | | (Parser) | |(Observer)|
  └──────────┘ └──────────┘ └──────────┘ └──────────┘
         |           |          |          |
         v           v          v          v
  ┌──────────────────────────────────────────────────┐
  │             Shared Tool Library                   │
  │  shell / files / planner / search / bypass / sys  │
  └──────────────────────────────────────────────────┘
```

All agents are LlamaIndex `FunctionAgent` instances except the Orchestrator, which is a pure Python dispatcher. The Orchestrator does not use an LLM -- it simply runs agents on a timer with predefined task prompts.

### Scheduled Maintenance

The orchestrator runs agents on a schedule:

- **Planner**: Every 5 minutes
- **Executor**: Every 1 minute (up to 5 concurrent)
- **Parser**: Every 1 minute (up to 5 concurrent)
- **Monitor**: Every 120 minutes

> **Note**: Agent schedules are currently configured in code. A future
> enhancement will add persistent schedule management via CLI commands.

### Manual CLI vs Autonomous Agent Operations

| Operation | Manual CLI Command | Autonomous Agent |
|-----------|-------------------|------------------|
| Run recurring pipeline cycle | `uv run news48 fetch && uv run news48 download --limit 10 && uv run news48 parse --limit 10 && uv run news48 cleanup purge --force` | Planner + Executor + Parser loop |
| Purge old articles | `uv run news48 cleanup purge --force` | Executor via explicit cleanup plan steps |
| Check database health | `uv run news48 cleanup health` | Monitor Agent (every 120m) |
| View retention status | `uv run news48 cleanup status` | Monitor Agent (alerts) |
| View system stats | `uv run news48 stats` | Monitor Agent report context |
| Read stored article content | `uv run news48 articles content <id> --json` | Executor during fact-check plan execution |
| Set fact-check verdict | `uv run news48 articles check <id> --status verified --result "..." --json` | Executor during fact-check plan execution |
| List fact-checked articles | `uv run news48 articles list --status fact-checked` | Planner + Executor recurring planning and execution |

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

Or run the agent system autonomously:

```bash
# Run specific roles explicitly
uv run news48 agents run --agent planner
uv run news48 agents run --agent executor
uv run news48 agents run --agent parser

# Or let the Orchestrator handle it on schedule
uv run news48 agents run
```

---

## Next Steps

- See [CLI Testing Guide](cli-testing-guide.md) for detailed command reference
- Check [README.md](../README.md) for installation and configuration
- Review [pyproject.toml](../pyproject.toml) for project dependencies
- See [Planner Agent Instructions](../agents/instructions/planner.md) for planning details
- See [Executor Agent Instructions](../agents/instructions/executor.md) for execution details
- See [Parser Agent Instructions](../agents/instructions/parser.md) for parsing details
- See [Monitor Agent Instructions](../agents/instructions/monitor.md) for monitoring details
