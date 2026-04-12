# 🗞️ news48

Autonomous news ingestion and verification pipeline with self-learning AI agents ⚙️

 `news48` collects feed entries, downloads article pages, parses structured content with an LLM, applies retention policy, and continuously coordinates recurring work through scheduled agents — **agents that learn from their mistakes and get smarter over time**.

## ✨ What it does

- 📡 Feed ingestion from RSS and Atom sources
- 🔄 Article lifecycle pipeline: fetch -> download -> parse
- 🧪 Fact-check workflow support with verdict storage
- 🧹 Retention and database health tooling
- 🤖 Autonomous orchestration with planner, executor, parser, and monitor agents
- 🧠 **Self-learning agents** that persist lessons across runs

## 🧠 Active autonomous architecture

 The current runtime model uses four scheduled agents:

 - `planner`: detects gaps and creates executable plans
 - `executor`: claims one plan, executes steps, and verifies outcomes
 - `parser`: claims downloaded articles from the database and parses them autonomously
 - `monitor`: gathers health metrics, classifies status, and emits reports

 ```text
                      Orchestrator
                    agents start daemon
                            |
            +-------+-------+-------+
            |       |       |       |
         Planner Executor Parser  Monitor
          plans    runs   parses  observes
            |       |       |       |
            +-------+-------+-------+
                    |               |
           news48 CLI & tools    .lessons.md
                                 (agents learn
                                  across runs)
 ```

 Reference implementation:
- Orchestration loop in `agents/orchestrator.py`
- Schedules in `agents/schedules.py`
- CLI entry points in `commands/agents.py`

## 🧠 Agents that learn

news48 agents **learn from their mistakes** and accumulate knowledge across runs. When an agent discovers something — correct command syntax after a failed attempt, a process insight, a feed-specific quirk, or an error recovery technique — it saves the lesson to a persistent file (`.lessons.md`). On every subsequent run, all accumulated lessons are automatically loaded into every agent's prompt.

This means the system **gets smarter over time**:

```
Run 1:  Executor fails with wrong timeout → discovers 600s is correct → saves lesson
Run 2:  Executor starts with "timeout for fact-check should be 600s" already in memory
```

### How it works

- **Save**: Agents call the `save_lesson` tool whenever they discover something worth remembering
- **Load**: At startup, `compose_agent_instructions()` reads `.lessons.md` and appends all lessons to the system prompt
- **Cross-pollination**: All agents see all lessons — executor learns from planner's insights, monitor learns from parser's quirks
- **Idempotent**: Duplicate lessons are automatically skipped
- **Human-auditable**: Lessons are stored as plain markdown, easy to read and prune

### What agents learn

| Category | Examples |
|----------|----------|
| Command Syntax | Correct flags, arguments, timeout values |
| Process Insights | How workflows actually behave in practice |
| Feed Quirks | Non-standard date formats, rate limits, HTML structures |
| Error Recovery | What fixes specific error conditions |
| Best Practices | Patterns that lead to better outcomes |
| Timing & Thresholds | Correct batch sizes, intervals, limits |

The lessons file is gitignored (instance-specific) and accumulates over time. See `agents/skills/shared/lessons-learned.md` for the agent-facing skill documentation.

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
 uv run news48 seed seed.txt

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
 uv run news48 agents run --agent parser
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

 - planner: every 5 minutes
 - executor: every 1 minute (up to 5 concurrent)
 - parser: every 1 minute (up to 5 concurrent)
 - monitor: every 120 minutes

 See schedule source in `agents/schedules.py`.

## 📚 Documentation map

 - Workflow guide: `docs/workflow-guide.md`
 - CLI test coverage: `docs/cli-testing-guide.md`
 - Agent tool inventory: `docs/agents-tools-inventory.md`
 - Architecture review: `plans/architecture-review.md`
 - Planner instructions: `agents/instructions/planner.md`
 - Executor instructions: `agents/instructions/executor.md`
 - Parser instructions: `agents/instructions/parser.md`
 - Monitor instructions: `agents/instructions/monitor.md`

## 🧬 Development and tests

 ```bash
 uv run pytest
 ```

 Key test suites include agent behavior, planner tools, lessons learned, streaming, and database claim paths.

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
