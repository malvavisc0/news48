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
| 🤖 **Autonomous Agents** | Planner, executor, parser, and monitor run on schedules |
| 🧠 **Self-Learning** | Agents persist lessons across runs and improve over time |

## 🏗️ Architecture

Four scheduled agents run under a single orchestrator daemon:

```
                    ┌─────────────┐
                    │ Orchestrator │
                    │ agents start │
                    └──────┬──────┘
           ┌───────┬───────┼───────┐
           ▼       ▼       ▼       ▼
       ┌───────┐┌───────┐┌──────┐┌───────┐
       │Planner││Executor││Parser││Monitor│
       │ plans ││  runs  ││parses││observes│
       └───┬───┘└───┬───┘└──┬───┘└───┬───┘
           └───────┬───────┘         │
                   ▼                 ▼
          news48 CLI & tools    .lessons.md
                              (shared memory)
```

| Agent | Role |
|-------|------|
| **Planner** | Detects gaps and creates executable plans |
| **Executor** | Claims a plan, executes steps, verifies outcomes |
| **Parser** | Claims downloaded articles and parses them autonomously |
| **Monitor** | Gathers health metrics, classifies status, emits reports |

> **Source:** orchestration loop in [`agents/orchestrator.py`](agents/orchestrator.py), schedules in [`agents/schedules.py`](agents/schedules.py), CLI entry points in [`commands/agents.py`](commands/agents.py).

## 🧠 Self-Learning Agents

news48 agents **learn from their mistakes** and accumulate knowledge across runs. When an agent discovers something — correct command syntax, a process insight, a feed-specific quirk, or an error recovery technique — it saves the lesson to `.lessons.md`. On every subsequent run, all accumulated lessons are loaded into every agent's prompt.

```
Run 1:  Executor fails with wrong timeout → discovers 600s works → saves lesson
Run 2:  Executor starts with "timeout for fact-check should be 600s" already loaded
```

**How it works:**

- **Save** — agents call `save_lesson` whenever they discover something worth remembering
- **Load** — `compose_agent_instructions()` reads `.lessons.md` and injects lessons into the system prompt
- **Cross-pollination** — all agents see all lessons (executor learns from planner, monitor learns from parser)
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

> The lessons file is gitignored (instance-specific). See [`agents/skills/shared/lessons-learned.md`](agents/skills/shared/lessons-learned.md) for the agent-facing skill documentation.

## 🚀 Quick Start

### Prerequisites

- Python **3.12+**
- [uv](https://docs.astral.sh/uv/) package manager
- An OpenAI-compatible LLM endpoint
- A [Byparr](https://github.com/TheBeastLT/Byparr) instance for downloading

### Installation

```bash
# 1. Install dependencies
uv sync

# 2. Configure environment
cp .env.example .env
```

Edit `.env` and set the required variables:

| Variable | Required | Description |
|----------|:--------:|-------------|
| `DATABASE_PATH` | ✅ | Path to SQLite database |
| `BYPARR_API_URL` | ✅ | Byparr service URL |
| `API_BASE` | ✅ | LLM API base URL |
| `API_KEY` | ✅ | LLM API key |
| `MODEL` | ✅ | Model identifier |
| `CONTEXT_WINDOW` | | Context window size (default: 1048576) |
| `SEARXNG_URL` | | SearXNG instance for search |
| `SMTP_HOST` | | SMTP server for monitor email alerts |
| `SMTP_PORT` | | SMTP port (default: 587) |
| `SMTP_USER` | | SMTP username |
| `SMTP_PASS` | | SMTP password |
| `SMTP_FROM` | | Sender email address |
| `MONITOR_EMAIL_TO` | | Recipient for monitor alerts |

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
```

### Agent Operations

**One-shot runs:**

```bash
uv run news48 agents run --agent planner
uv run news48 agents run --agent executor
uv run news48 agents run --agent parser
uv run news48 agents run --agent monitor
```

**Continuous autonomous mode:**

```bash
uv run news48 agents start          # start the orchestrator daemon
uv run news48 agents status --json  # check running agents
uv run news48 agents dashboard      # live dashboard
uv run news48 agents stop           # graceful shutdown
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
