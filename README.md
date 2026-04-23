<div align="center">

# 🗞️ news48

**Autonomous news ingestion and verification pipeline with self-learning AI agents**

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-3776AB?logo=python&logoColor=white)](#prerequisites)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![uv](https://img.shields.io/badge/pkg-uv-DE5FE9?logo=uv&logoColor=white)](#quick-start)

</div>

---

news48 collects feed entries, downloads article pages, parses structured content with an LLM, applies retention policy, and continuously coordinates recurring work through scheduled agents — **agents that learn from their mistakes and get smarter over time**.

## Table of Contents

- [Features](#-features)
- [Architecture](#-architecture)
- [Self-Learning Agents](#-self-learning-agents)
- [Quick Start](#-quick-start)
- [Usage](#-usage)
  - [Manual Pipeline](#manual-pipeline)
  - [Agent Operations](#agent-operations)
- [Docker](#-docker)
  - [Seeding the Database](#seeding-the-database)
  - [Development](#docker-development)
  - [Production](#docker-production)
- [Schedule Defaults](#-schedule-defaults)
- [Documentation](#-documentation)
- [Development](#-development)
- [License](#-license)

## ✨ Features

| | |
|---|---|
| 📡 **Feed Ingestion** | RSS and Atom sources with automatic deduplication |
| 🔄 **Article Pipeline** | End-to-end lifecycle: fetch → download → parse |
| 🧪 **Fact-Checking** | Integrated verification workflow with verdict storage |
| 🧹 **Retention & Health** | Automated cleanup and database health tooling |
| 🤖 **Autonomous Agents** | Sentinel, executor, parser, and fact-checker run on schedules |
| 🧠 **Self-Learning** | Agents persist lessons across runs and improve over time |

## 🏗️ Architecture

Four scheduled agents run through Periodiq-scheduled Dramatiq actors backed by Redis:

```
                    ┌─────────────┐
                    │  Periodiq   │
                    │ cron enqueue│
                    └──────┬──────┘
           ┌───────┬───────┼───────┐
            ▼       ▼       ▼       ▼
        ┌────────┐┌────────┐┌─────┐┌────────────┐
        │Sentinel││Executor││Parser││Fact-checker│
        │observes││  runs  ││parses││  verifies  │
        └───┬────┘└───┬────┘└──┬──┘└─────┬──────┘
            └───────┬───────┘          │
                    ▼                  ▼
                Redis queues      .lessons.md
                    │            (shared memory)
                    ▼
           Dramatiq workers + news48 CLI & tools
```

| Agent | Role |
|-------|------|
| **Sentinel** | Observes system health, evaluates thresholds, creates fix plans |
| **Executor** | Claims a plan, executes steps, verifies outcomes |
| **Parser** | Claims downloaded articles and parses them autonomously |
| **Fact-checker** | Verifies claims by searching evidence and recording verdicts |

> **Source:** Dramatiq actors in [`news48/core/agents/actors.py`](news48/core/agents/actors.py), Periodiq cron schedules in [`news48/core/agents/actors.py`](news48/core/agents/actors.py), CLI entry points in [`news48/cli/commands/agents.py`](news48/cli/commands/agents.py).

## 🧠 Self-Learning Agents

news48 agents **learn from their mistakes** and accumulate knowledge across runs. When an agent discovers something — correct command syntax, a process insight, a feed-specific quirk, or an error recovery technique — it saves the lesson to `.lessons.md`. On every subsequent run, all accumulated lessons are loaded into every agent's prompt.

```
Run 1:  Executor fails with wrong timeout → discovers 600s works → saves lesson
Run 2:  Executor starts with "timeout for fact-check should be 600s" already loaded
```

**How it works:**

- **Save** — agents call `save_lesson` whenever they discover something worth remembering
- **Load** — `compose_agent_instructions()` reads `.lessons.md` and injects lessons into the system prompt
- **Cross-pollination** — all agents see all lessons (executor learns from sentinel, fact-checker learns from parser)
- **Idempotent** — duplicate lessons are automatically skipped
- **Human-auditable** — plain markdown, easy to read and prune

**What agents learn:**

| Category | Examples |
|----------|----------|
| Command Syntax | Correct flags, arguments, timeout values |
| Process Insights | How workflows actually behave in practice |
| Feed Quirks | Non-standard date formats, rate limits, HTML structures |
| Error Recovery | What fixes specific error conditions |
| Best Practices | Patterns that lead to better outcomes |
| Timing & Thresholds | Correct batch sizes, intervals, limits |

> The lessons file is gitignored (instance-specific). See [`news48/core/agents/skills/shared/lessons-learned.md`](news48/core/agents/skills/shared/lessons-learned.md) for the agent-facing skill documentation.

## 🚀 Quick Start

### Prerequisites

- Python **3.12+**
- [uv](https://docs.astral.sh/uv/) package manager
- An OpenAI-compatible LLM endpoint
- A [Byparr](https://github.com/TheBeastLT/Byparr) instance for downloading

### Installation

```bash
# 1. Install dependencies (CLI + web)
uv sync --extra all

# 2. Configure environment
cp .env.example .env
```

**Install extras:**

```bash
uv sync --extra cli    # CLI + agents only
uv sync --extra web    # Web server only
uv sync --extra all    # Everything
```

Edit `.env` and set the required variables:

| Variable | Required | Description |
|----------|:--------:|-------------|
| `DATABASE_URL` | ✅ | SQLAlchemy database URL for MySQL |
| `REDIS_URL` | | Redis broker URL for Dramatiq + Periodiq |
| `BYPARR_API_URL` | ✅ | Byparr service URL |
| `API_BASE` | ✅ | LLM API base URL |
| `API_KEY` | ✅ | LLM API key |
| `MODEL` | ✅ | Model identifier |
| `CONTEXT_WINDOW` | | Context window size (default: 1048576) |
| `SEARXNG_URL` | | SearXNG instance for search |
| `SMTP_HOST` | | SMTP server for sentinel email alerts |
| `SMTP_PORT` | | SMTP port (default: 587) |
| `SMTP_USER` | | SMTP username |
| `SMTP_PASS` | | SMTP password |
| `SMTP_FROM` | | Sender email address |
| `MONITOR_EMAIL_TO` | | Recipient for sentinel alerts |

```bash
# 3. Verify installation
uv run news48 --help
```

## 📖 Usage

### Manual Pipeline

```bash
# Seed feeds from a file
uv run news48 seed seed.txt

# Run pipeline stages
uv run news48 fetch
uv run news48 download --limit 10
uv run news48 parse --limit 10

# Inspect system state
uv run news48 stats --json
uv run news48 cleanup status --json
uv run news48 cleanup health --json

# Manage lessons learned
uv run news48 lessons list                          # view all lessons
uv run news48 lessons list --agent executor --json  # filter by agent
uv run news48 lessons add --agent executor \
  --category "Command Syntax" \
  --lesson "Use timeout=600 for fact-check"         # add manually
```

### Agent Operations

**One-shot runs:**

```bash
uv run news48 agents run --agent sentinel
uv run news48 agents run --agent executor
uv run news48 agents run --agent parser
uv run news48 agents run --agent fact_checker
```

**Continuous autonomous mode:**

```bash
dramatiq news48.core.agents.actors --processes 1 --threads 8  # run workers
periodiq news48.core.agents.actors                               # enqueue cron tasks
uv run news48 agents status --json                  # inspect queues and schedules
```

`agents start`, `agents stop`, and `agents dashboard` are no longer part of the operational model. Docker manages worker lifecycle, while Redis stores queue state.

## 🐳 Docker

news48 can run entirely in Docker with separate containers for the web interface, MySQL, Redis, Dramatiq workers, Periodiq scheduler, SearXNG, and Byparr.

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/)
- An OpenAI-compatible LLM endpoint
- API keys configured in `.env`

### Setup

```bash
# One-time setup
cp .env.example .env
# Edit .env with your API keys
```

### Seeding the Database

Before the pipeline can fetch articles, the database needs feed URLs. Create a `seed.txt` file in the project root with one RSS/Atom URL per line:

```bash
# seed.txt
https://feeds.arstechnica.com/arstechnica/index
https://feeds.bbci.co.uk/news/rss.xml
https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml
```

When the worker stack starts, the sentinel agent automatically detects an empty database and creates a seed plan for the executor. The executor then runs `news48 seed seed.txt` — so seeding happens automatically as long as `seed.txt` is accessible inside the worker container.

**Development** — the project root is mounted at `/app`, so `seed.txt` is automatically available at `/app/seed.txt`.

**Production** — the project root is not mounted. Either:

- Build the image with `seed.txt` present in the project root (it is not excluded by `.dockerignore` and gets copied via `COPY . .`), or
- Mount it at runtime:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm \
  -v ./seed.txt:/app/seed.txt:ro \
  dramatiq-worker news48 seed /app/seed.txt
```

You can also seed manually at any time:

```bash
# Development
docker compose exec dramatiq-worker news48 seed /app/seed.txt

# Production
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec \
  dramatiq-worker news48 seed /app/seed.txt
```

Verify feeds were added:

```bash
docker compose exec dramatiq-worker news48 feeds list
```

### Docker Development

```bash
# Start all services with live reload
docker compose up

# Web UI available at http://localhost:8765
# Code changes auto-reload via volume mount
# RedisInsight available at http://localhost:8001
# Dozzle logs UI available at http://localhost:9999

# Run CLI commands
docker compose exec dramatiq-worker news48 stats
docker compose exec dramatiq-worker news48 feeds list

# Run one-off commands
docker compose run --rm dramatiq-worker news48 seed /app/seed.txt

# View logs
docker compose logs -f dramatiq-worker
docker compose logs -f periodiq-scheduler
docker compose logs -f web
docker compose logs -f redis

# Stop everything
docker compose down

# Fresh start (removes data)
docker compose down -v
```

### Docker Production

```bash
# Start production stack
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Web UI available at http://localhost:8000

# Check status
docker compose ps
docker compose logs -f web

# Backup MySQL database
docker compose exec mysql mysqldump -unews48 -pnews48 news48 > backup.sql

# Update to new version
docker compose -f docker-compose.yml -f docker-compose.prod.yml build --no-cache
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Stop production
docker compose -f docker-compose.yml -f docker-compose.prod.yml down
```

### Worker Observability

There is **no dedicated Dramatiq admin UI** in the current stack. Use the included Docker and Redis tooling instead:

- **RedisInsight** at `http://localhost:8001` — inspect Redis keys, queues, and broker state
- **Dozzle** at `http://localhost:9999` in development — inspect container logs for [`dramatiq-worker`](docker-compose.yml) and [`periodiq-scheduler`](docker-compose.yml)
- [`uv run news48 agents status --json`](README.md:193) — inspect queue and schedule state from the CLI

This means Dramatiq execution is currently observed through Redis, logs, and the CLI rather than through a standalone Dramatiq dashboard.

### Architecture

| Service | Image | Port | Role |
|---------|-------|------|------|
| `web` | news48-web (built) | 8000 | FastAPI web interface |
| `mysql` | mysql:8.0 | 3306 | Primary relational database |
| `redis` | redis/redis-stack | 6379 / 8001 | Dramatiq broker + RedisInsight |
| `dramatiq-worker` | news48-worker (built) | none | Executes agents and pipeline actors |
| `periodiq-scheduler` | news48-worker (built) | none | Enqueues scheduled agent and pipeline work |
| `searxng` | searxng/searxng:latest | 8080 (internal) | Meta-search engine |
| `dozzle` | amir20/dozzle:latest | 8080 | Container log viewer |
| `byparr` | ghcr.io/thephaseless/byparr:main | 8191 (internal) | Anti-bot bypass |

## 🔌 MCP Integration

news48 exposes operations via the [Model Context Protocol](https://modelcontextprotocol.io/) so AI assistants can interact with your news pipeline.

### Local MCP Server (stdio)

Start the local MCP server for Claude Desktop, Cursor, etc.:

```bash
uv run news48 mcp serve
```

Configure your AI assistant:

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

**Available tools:** `fetch_feeds`, `list_feeds`, `search_articles`, `get_article_detail`, `get_stats`, `parse_article`

### Remote MCP Endpoint (Streamable HTTP)

The web app exposes an authenticated MCP endpoint at `/mcp/`. Manage API keys with:

```bash
uv run news48 mcp create-key --label "Claude Desktop"
uv run news48 mcp list-keys
uv run news48 mcp revoke-key n48-abc123...
```

Remote clients connect with a Bearer token:

```json
{
  "mcpServers": {
    "news48-remote": {
      "url": "https://your-domain.com/mcp/",
      "headers": {
        "Authorization": "Bearer n48-your-api-key-here"
      }
    }
  }
}
```

## 🧬 Development

```bash
# Run test suite
uv run pytest

# Format code
uv run black .
uv run isort .
```

Key test suites cover agent behavior, planner tools, lessons learned, streaming, and database claim paths.

## 📄 License

MIT — see [LICENSE](LICENSE) for details.
