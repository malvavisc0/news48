<div align="center">

# 🗞️ news48

**Autonomous news ingestion & verification pipeline with self-learning AI agents**

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-3776AB?logo=python&logoColor=white)](#prerequisites)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![uv](https://img.shields.io/badge/pkg-uv-DE5FE9?logo=uv&logoColor=white)](#quick-start)

<br />

Collect → Download → Parse → Fact-check — on repeat, with agents that learn.

</div>

---

## 📖 Table of Contents

- [What Is It?](#-what-is-it)
- [Web Interface](#-web-interface)
- [Pipeline](#-pipeline)
- [Agents](#-agents)
- [Autonomous Operation](#-autonomous-operation)
- [CLI Reference](#-cli-reference)
- [Quick Start](#-quick-start)
- [Docker](#-docker)
- [MCP Integration](#-mcp-integration)
- [Development](#-development)
- [License](#-license)

---

## 🔍 What Is It?

news48 is a self-hosted news pipeline that:

1. **Ingests** RSS/Atom feeds from sources you choose
2. **Downloads** full article content (with anti-bot bypass)
3. **Parses** unstructured HTML into structured data via LLM
4. **Fact-checks** claims against external evidence
5. **Purges** stale data on a 48-hour retention window

All of this runs **autonomously** through four AI agents that schedule themselves via Dramatiq + Periodiq. The agents also **learn from mistakes** — saving lessons that carry across runs so they get smarter over time.

---

## 🌐 Web Interface

news48 ships a FastAPI web interface that displays the last 48 hours of verified news. In Docker it's available at `http://localhost:8765` (dev) or `http://localhost:8000` (prod).

### Pages

| Route | Description |
|-------|-------------|
| `/` | Homepage — top 10 stories, trending topics, expiring articles |
| `/all` | All stories with optional tone filter (`?sentiment=positive\|neutral\|negative`) |
| `/category/{slug}` | Category view with tone filter (e.g. `/category/politics?sentiment=negative`) |
| `/article/{id}/{slug}` | Article detail with fact-check breakdown and related coverage |
| `/cluster/{slug}` | Topic cluster — all stories sharing a tag |
| `/docs` | Architecture overview & MCP setup guide (loads autonomous operation score) |
| `/monitor` | Internal monitor dashboard — server-rendered pipeline stats (`noindex`) |
| `/api/stats` | JSON stats API (requires `Authorization: Bearer <mcp-api-key>`) |
| `/sitemap.xml` | Auto-generated XML sitemap |
| `/robots.txt` | Robots file with sitemap reference |
| `/llms.txt` | Machine-readable system description for AI assistants |
| `/health` | Health check endpoint (`{"status": "ok"}`) |

### Features

- **AI-rewritten summaries** — clear, plain-English summaries for every parsed story
- **Fact-check breakdown** — per-claim verdicts (verified, disputed, mixed, unverifiable) with evidence
- **Tone filter** — filter stories by sentiment (positive, neutral, negative) across all pages
- **Trending topics** — auto-generated topic clusters from article tags
- **Expiring stories** — catch time-sensitive reporting before it leaves the 48-hour window
- **Deduplication** — same story from multiple sources is shown once per category
- **Category normalization** — consistent category names (e.g. `artificial-intelligence` and `artificial intelligence` are merged)
- **SEO-friendly** — canonical URLs, Open Graph tags, JSON-LD structured data, XML sitemap
- **Rate limiting** — 120 req/min general, 20 req/min for search
- **Security headers** — X-Content-Type-Options, X-Frame-Options, CSP, Referrer-Policy

---

## 🔁 Pipeline

```
 seed.txt ──► seed ──► fetch ──► download ──► parse ──► fact-check
                │          │          │           │           │
                ▼          ▼          ▼           ▼           ▼
             DB feeds   DB articles  HTML → MD  structured   verdicts
                                                    data
```

| Stage | Command | What it does |
|-------|---------|-------------|
| 🌱 Seed | `news48 seed seed.txt` | Load feed URLs into the database |
| 📡 Fetch | `news48 fetch` | Pull RSS/Atom entries → store as articles |
| ⬇️ Download | `news48 download` | Fetch full article HTML (with bypass) |
| 🧩 Parse | `news48 parse` | Extract title, summary, categories, sentiment via LLM |
| 🔬 Fact-check | `news48 fact-check` | Verify claims against evidence, record verdicts |
| 🧹 Cleanup | `news48 cleanup purge` | Remove articles older than 48 hours |
| 🧹 Summaries | `news48 cleanup summaries` | Clean truncation markers from summaries |

Most commands support `--json` for machine-readable output and `--limit` to control batch size.

---

## 🤖 Agents

Four agents run on schedules through **Periodiq → Redis → Dramatiq**:

| Agent | Cron | What it does |
|-------|------|-------------|
| **Sentinel** | `*/5 * * * *` | Monitors health, creates fix plans, deletes bad feeds |
| **Executor** | `* * * * *` | Claims a plan, runs its steps, verifies outcomes |
| **Parser** | `* * * * *` | Claims articles, runs LLM parsing autonomously |
| **Fact-checker** | `*/10 * * * *` | Verifies claims, searches evidence, records verdicts |

### 🧠 Self-Learning

Agents **save lessons** when they discover something useful. On the next run, all accumulated lessons are injected into every agent's prompt:

```
Run 1:  Executor fails with wrong timeout → discovers 600s works → saves lesson
Run 2:  Executor starts with "timeout for fact-check should be 600s" already loaded
```

Lessons are stored in `data/lessons.db` (SQLite), cross-pollinated across agents, and human-auditable.

```bash
news48 lessons list                              # view all
news48 lessons list --agent executor --json      # filter by agent
news48 lessons add -a executor -c "Timing" -l "Use 600s timeout for fact-checks"
```

---

## 🎯 Autonomous Operation

news48 is designed to run **without human intervention**. Every capability is measured by a rigorous **Autonomous Operation Score** — a weighted assessment across six dimensions that evaluates how well the system starts, monitors, heals, scales, optimizes, and contains errors on its own.

### Current Score: **4.9 / 5.0** — Autonomous

> System runs unattended for extended periods. Human involvement only for strategic decisions.

| Dimension | Weight | Score | What it measures |
|-----------|:------:|:-----:|-----------------|
| **Self-starting** | 15% | 5.0 | Zero-to-running without human help — auto-seeding, startup recovery, Periodiq scheduling |
| **Self-monitoring** | 20% | 4.7 | Health observation, structured reports, email alerts, canonical thresholds |
| **Self-healing** | 25% | 5.0 | Background download/parse/feed loops, plan deadlock healing, retry logic |
| **Self-scaling** | 10% | 5.0 | Parallel wave execution, concurrent actor instances, batch-repeat patterns |
| **Self-optimizing** | 10% | 5.0 | Cross-run lesson persistence, feed curation, plan deduplication |
| **Error containment** | 20% | 5.0 | Quality gates, retry limits, failure isolation, runtime timeouts, error taxonomy |

### How It Works

Every checkpoint is enforced at one of two layers:

- **`[code]`** — Deterministic Python code paths (e.g., `StartupRecoveryMiddleware` runs recovery on every worker boot)
- **`[instruction]`** — Agent skill files that define rules the LLM follows (e.g., `fail-safely.md` mandates breaking loops after 5 repeated errors)
- **`[both]`** — Defence in depth with code + instructions working together

The full methodology — all 40 checkpoints, verification procedures, and scoring rubric — is documented in [`docs/autonomous-operation-score.md`](docs/autonomous-operation-score.md). The latest assessment is loaded dynamically on the `/docs` page.

### Score Levels

| Range | Level | Meaning |
|-------|-------|---------|
| 4.5 – 5.0 | **Autonomous** | Runs unattended. Human only for strategic decisions. |
| 3.5 – 4.4 | **Supervised** | Autonomous under normal conditions. Human needed for edge cases. |
| 2.5 – 3.4 | **Assisted** | Handles happy path. Human needed for failures and recovery. |
| 1.5 – 2.4 | **Manual** | Frequent human input required. |
| 1.0 – 1.4 | **Prototype** | Only runs with direct supervision. |

---

## 📋 CLI Reference

### Pipeline Commands

```bash
news48 seed <file>              # Load feed URLs from file
news48 fetch                    # Pull RSS/Atom feeds
news48 download                 # Download article content
news48 parse                    # Parse articles with LLM
news48 fact-check               # Fact-check parsed articles
news48 briefing                 # Structured news briefing (top stories, trending, stats)
news48 doctor                   # Health check of all external services
news48 stats                    # Show system statistics
```

### Resource Management

```bash
# Feeds
news48 feeds list                          # List all feeds
news48 feeds add <url>                     # Add a feed
news48 feeds info <url-or-id>              # Feed details
news48 feeds update <url-or-id> -t "Title" # Update metadata
news48 feeds delete <url-or-id>            # Delete feed + articles
news48 feeds rss --hours 48 --output feed.xml  # Generate RSS

# Articles
news48 articles list --status parsed       # List by status
news48 articles info <id-or-url>           # Article details
news48 articles content <id-or-url>        # Show content
news48 articles update <id> --content-file <path>  # Update fields
news48 articles delete <id-or-url>         # Delete article
news48 articles reset <id> --all           # Reset failure flags
news48 articles feature <id>               # Mark as featured
news48 articles breaking <id>              # Mark as breaking
news48 articles check <id> -s verified     # Set fact-check result
news48 articles claims <id>                # Show per-claim verdicts

# Fetches
news48 fetches list                        # View fetch history
```

### Search

```bash
news48 search articles "climate change"                    # Full-text search
news48 search articles "election" --sentiment negative -l 5  # Filtered
```

### Agents & Plans

```bash
news48 agents status                 # Queue depths + cron schedules
news48 agents run -a parser          # Run one agent (enqueue to Dramatiq)
news48 agents run -a parser --inline # Run inline (debug, no Redis needed)

news48 plans list                    # List all plans
news48 plans list -s pending         # Filter by status
news48 plans show <plan-id>          # Show plan details
news48 plans cancel <plan-id>        # Cancel a plan
news48 plans remediate --apply       # Repair plan corruption
```

### Observability

```bash
news48 lessons list                  # View agent lessons
```

### Retention & Health

```bash
news48 cleanup status                # Retention policy stats
news48 cleanup purge                 # Purge old articles (default: 48h)
news48 cleanup purge --dry-run       # Preview without deleting
news48 cleanup health                # Database connectivity check
news48 cleanup summaries             # Clean truncation markers from summaries
news48 cleanup summaries --dry-run   # Preview summary cleaning
```

### Web & MCP

```bash
news48 mcp serve                     # Start MCP server (stdio)
news48 mcp create-key --label "Dev"  # Create API key
news48 mcp list-keys                 # List active keys
news48 mcp revoke-key <key>          # Revoke a key
```

> 💡 **Tip:** Append `--json` to any command for machine-readable output.

---

## 🚀 Quick Start

### Prerequisites

- Python **3.12+**
- [uv](https://docs.astral.sh/uv/) package manager
- An OpenAI-compatible LLM endpoint
- A [Byparr](https://github.com/TheBeastLT/Byparr) instance

### Install

**Option A — Docker (recommended):**

One-liner install:
```bash
curl -fsSL https://raw.githubusercontent.com/malvavisc0/news48/master/scripts/install.sh | bash
```

Or clone and run manually:
```bash
git clone https://github.com/malvavisc0/news48.git && cd news48
./scripts/install.sh
```

The interactive installer clones the repository, checks prerequisites, prompts for deployment mode (GPU or external LLM), generates secure passwords, and launches all services.

**Option B — Local (uv):**

```bash
git clone https://github.com/malvavisc0/news48.git && cd news48
uv sync --extra all
cp .env.example .env
# Edit .env with your API keys (see table below)
uv run news48 --help
```

**Extras:**

```bash
uv sync --extra cli    # CLI + agents only
uv sync --extra web    # Web server only
uv sync --extra all    # Everything
```

### Environment Variables

| Variable | Required | Description |
|----------|:--------:|-------------|
| `DATABASE_URL` | ✅ | SQLAlchemy database URL (MySQL) |
| `BYPARR_API_URL` | ✅ | Byparr service URL |
| `API_BASE` | ✅ | LLM API base URL |
| `API_KEY` | ✅ | LLM API key |
| `MODEL` | ✅ | Model identifier |
| `REDIS_URL` | | Redis URL for Dramatiq (required for agents) |
| `SEARXNG_URL` | | SearXNG for fact-checker evidence search |
| `CONTEXT_WINDOW` | | Context window size (default: 1048576) |
| `WEB_HOST` | | Web server host (default: `0.0.0.0`) |
| `WEB_PORT` | | Web server port (default: `8000`) |
| `PARSER_CONCURRENCY` | | Parser agent concurrency (default: `8`) |
| `ARTICLE_EXTRACTION` | | Body extraction mode: `trafilatura` or `none` (default: `trafilatura`) |
| `SMTP_HOST` | | SMTP host for sentinel email alerts |
| `SMTP_PORT` | | SMTP port (default: 587) |
| `SMTP_USER` | | SMTP username |
| `SMTP_PASS` | | SMTP password |
| `SMTP_FROM` | | Sender email address |
| `MONITOR_EMAIL_TO` | | Recipient for sentinel alerts |
| `HF_TOKEN` | | HuggingFace token for gated models (Docker GPU deployments) |

### Run It

```bash
# 1. Seed feeds
uv run news48 seed seed.txt

# 2. Fetch articles
uv run news48 fetch

# 3. Download content
uv run news48 download --limit 10

# 4. Parse with LLM
uv run news48 parse --limit 10

# 5. Check stats
uv run news48 stats
```

---

## 🐳 Docker

news48 runs entirely in Docker with separate containers for each service.

### Services

| Service | Port | Role |
|---------|------|------|
| `web` | 8000 | FastAPI web interface |
| `mysql` | 3306 | Primary database |
| `redis` | 6379 | Dramatiq broker + RedisInsight (8001) |
| `dramatiq-worker` | — | Executes agents and pipeline actors |
| `periodiq-scheduler` | — | Enqueues scheduled work |
| `searxng` | 8080† | Meta-search engine |
| `byparr` | 8191† | Anti-bot bypass |
| `dozzle` | 9999 | Container log viewer (dev) |

*† internal only*

### Development

```bash
# Start with live reload
docker compose up

# Web UI      → http://localhost:8765
# RedisInsight → http://localhost:8001
# Dozzle       → http://localhost:9999

# Run CLI inside container
docker compose exec dramatiq-worker news48 stats
docker compose exec dramatiq-worker news48 feeds list

# Logs
docker compose logs -f dramatiq-worker
docker compose logs -f web

# Stop
docker compose down        # keep data
docker compose down -v     # fresh start
```

### Production

```bash
# Start
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Web UI → http://localhost:8000

# Backup
docker compose exec mysql mysqldump -unews48 -pnews48 news48 > backup.sql

# Update
docker compose -f docker-compose.yml -f docker-compose.prod.yml build --no-cache
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Stop
docker compose -f docker-compose.yml -f docker-compose.prod.yml down
```

### External LLM (no local GPU)

Use `docker-compose.external-llm.yml` to skip the built-in llama.cpp server and point at any OpenAI-compatible endpoint instead:

```bash
# Set API_BASE in .env (examples):
#   API_BASE=http://host:7070/v1          # host llama.cpp
#   API_BASE=https://api.openai.com/v1    # OpenAI
#   API_BASE=https://api.groq.com/openai/v1  # Groq
#   API_BASE=http://host:11434/v1         # Ollama

docker compose -f docker-compose.yml -f docker-compose.external-llm.yml up -d
```

This disables the Docker llama.cpp container and model download — ideal for hosted LLM APIs or when running llama.cpp on the host machine.

### Seeding in Docker

The sentinel agent auto-detects an empty database and creates a seed plan — so if `seed.txt` is in the image, seeding happens automatically.

```bash
# Manual seed
docker compose exec dramatiq-worker news48 seed /app/seed.txt

# Verify
docker compose exec dramatiq-worker news48 feeds list
```

### Worker Observability

- **RedisInsight** → `http://localhost:8001` — inspect queues and broker state
- **Dozzle** → `http://localhost:9999` — container log viewer
- **CLI** → `news48 agents status --json` — queue depths and cron schedules

---

## 🔌 MCP Integration

news48 exposes tools via the [Model Context Protocol](https://modelcontextprotocol.io/) so AI assistants can interact with your pipeline.

### Local Server (stdio)

No auth required — ideal for Claude Desktop, Cursor, etc.

```bash
uv run news48 mcp serve
```

```json
{
  "mcpServers": {
    "news48": {
      "command": "news48",
      "args": ["mcp", "serve"]
    }
  }
}
```

**Tools:** `get_briefing`, `search_news`, `get_article`, `browse_category`, `list_categories`, `list_countries`

### Remote Endpoint (HTTP)

The web app exposes an authenticated endpoint at `/mcp`. Keys are stored in Redis.

```bash
# Create a key
uv run news48 mcp create-key --label "Claude Desktop"
# → Created MCP API key: n48-aBcDeFgHiJkLmNoPqRsTuVwXyZ...
# ⚠️  Copy it now — it can't be retrieved later

# List keys (masked)
uv run news48 mcp list-keys

# Revoke a key
uv run news48 mcp revoke-key n48-...
```

```json
{
  "mcpServers": {
    "news48-remote": {
      "url": "https://your-domain.com/mcp",
      "headers": {
        "Authorization": "Bearer n48-your-api-key-here"
      }
    }
  }
}
```

Both `/mcp` and `/mcp/` work — the endpoint handles both paths without redirects, which is critical for browser-based MCP clients (Inspector, Claude, Cursor). CORS preflight (`OPTIONS`) is handled directly by the endpoint with `Access-Control-Allow-Origin: *`.

**Tools:** `get_briefing`, `search_news`, `get_article`, `browse_category`, `list_categories`, `list_countries`

> 🔒 All keys are prefixed `n48-` for secret scanner detection. If Redis is unreachable, all MCP requests are denied (fail-closed).

<details>
<summary><strong>Troubleshooting MCP connections</strong></summary>

| Symptom | Cause | Fix |
|---------|-------|-----|
| `Failed to fetch (check CORS?)` | Browser CORS preflight blocked | Verify the web container is running; check no reverse proxy strips `Access-Control-*` headers |
| `401 Unauthorized` | Missing or invalid API key | Create a key with `news48 mcp create-key` and pass it in the `Authorization` header |
| `307 Temporary Redirect` | Old server version redirecting `/mcp` → `/mcp/` | Update to latest — both paths now work without redirects |

For full details see [`docs/mcp-tools.md`](docs/mcp-tools.md).
</details>

---

## 🧬 Development

```bash
# Run tests
uv run pytest

# Format
uv run black .
uv run isort .
```

---

## 📄 License

MIT — see [LICENSE](LICENSE) for details.