# 🗞️ news48

Autonomous news ingestion and verification pipeline with a planner-executor-monitor agent loop ⚙️

 `news48` collects feed entries, downloads article pages, parses structured content with an LLM, applies retention policy, and continuously coordinates recurring work through scheduled agents.

## ✨ What it does

- 📡 Feed ingestion from RSS and Atom sources
- 🔄 Article lifecycle pipeline: fetch -> download -> parse
- 🧪 Fact-check workflow support with verdict storage
- 🧹 Retention and database health tooling
- 🤖 Autonomous orchestration with planner, executor, and monitor agents

## 🧠 Active autonomous architecture

 The current runtime model uses three scheduled agents:

 - `planner`: detects gaps and creates executable plans
 - `executor`: claims one plan, executes steps, verifies outcomes
 - `monitor`: gathers health metrics and emits alerts and reports

 ```text
                    Orchestrator
                  agents start daemon
                          |
             +------------+------------+
             |            |            |
          Planner      Executor      Monitor
           plans         runs        observes
             |            |            |
             +------------+------------+
                          |
                 news48 CLI and tools
 ```

 Reference implementation:
- Orchestration loop in `agents/orchestrator.py`
- Schedules in `agents/schedules.py`
- CLI entry points in `commands/agents.py`

## 🚀 Quick start

1) Install dependencies 📦

 ```bash
 uv sync
 ```

2) Configure environment 🔐

 ```bash
 cp .env.example .env
 ```

 Set at minimum:

 - `DATABASE_PATH`
 - `BYPARR_API_URL`
 - `API_BASE`
 - `MODEL`
 - `API_KEY`

 Optional for monitoring email:

 - `SMTP_HOST`
 - `SMTP_PORT`
 - `SMTP_USER`
 - `SMTP_PASS`
 - `SMTP_FROM`
 - `MONITOR_EMAIL_TO`

3) Verify CLI ✅

 ```bash
 uv run news48 --help
 ```

## 🛠️ Core manual workflow

 ```bash
 # seed feeds
 uv run news48 seed newsfeeds.seed.txt

 # run pipeline stages
 uv run news48 fetch
 uv run news48 download --limit 10
 uv run news48 parse --limit 10

 # inspect system
 uv run news48 stats --json
 uv run news48 cleanup status --json
 uv run news48 cleanup health --json
 ```

## 🤖 Agent operations

One-shot runs ⚡:

 ```bash
 uv run news48 agents run --agent planner
 uv run news48 agents run --agent executor
 uv run news48 agents run --agent monitor
 ```

Continuous autonomous scheduling ♻️:

 ```bash
 uv run news48 agents start
 ```

Status and control 🧭:

 ```bash
 uv run news48 agents status --json
 uv run news48 agents dashboard
 uv run news48 agents stop
 ```

## ⏱️ Current schedule defaults

 - planner: every 1 minute
 - executor: every 1 minute
 - monitor: every 1440 minutes

 See schedule source in `agents/schedules.py`.

## 📚 Documentation map

 - Workflow guide: `docs/workflow-guide.md`
 - CLI test coverage: `docs/cli-testing-guide.md`
 - Agent tool inventory: `docs/agents-tools-inventory.md`
 - Planner instructions: `agents/instructions/planner.md`
 - Executor instructions: `agents/instructions/executor.md`
 - Monitor instructions: `agents/instructions/monitor.md`

## 🧬 Development and tests

 ```bash
 uv run pytest
 ```

 Key test suites include agent behavior, planner tools, streaming, and database claim paths.
