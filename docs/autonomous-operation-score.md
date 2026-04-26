# Autonomous Operation Score — Measurement Guide

A repeatable methodology for scoring how well news48 operates without human intervention. This guide targets the **v4 architecture** with four agents: **Sentinel**, **Executor**, **Parser**, and **Fact-checker**, executed via **Dramatiq workers** with **Periodiq scheduling** and **Redis** as the message broker.

---

## How to Use This Document

1. Walk through each of the 6 dimensions below.
2. For every checkpoint, perform the **verification procedure** (codebase review and/or live test).
3. Record **PASS / FAIL / PARTIAL** for each checkpoint using the scoring rubric.
4. Compute the dimension score using the formula in each section.
5. Compute the overall score using the weighted formula at the bottom.
6. Record the date, per-checkpoint results (in `.scoring/latest-assessment.json`), and dimension scores in the **Score History** table.

---

## Scoring Rubric

| Result | Value | When to use |
|--------|-------|-------------|
| **PASS** | 1.0 | Capability is fully implemented. Code-enforced checkpoints: function/logic exists and is called. Instruction-enforced checkpoints: rules are clear, unambiguous, and complete. |
| **PARTIAL** | 0.5 | Capability is partially implemented, has edge cases, or has conflicting/ambiguous guidance. Also use when a code path exists but is incomplete, or when instruction rules exist but contradict another instruction. |
| **FAIL** | 0.0 | Capability is not implemented, or the verification procedure finds the claim is false. |

---

## Verification Tiers

Each checkpoint can be verified at two levels. Record which tier was used.

| Tier | Method | When to use |
|------|--------|-------------|
| **T1 — Codebase review** | `grep`, `read_file`, code inspection | Always available. Confirms the capability exists in code or instructions. |
| **T2 — Live validation** | Run the actual scenario against a live system | Confirms the capability works at runtime. Overrides T1 if results differ. |

If only T1 is performed, note it in the assessment. A full assessment should include T2 for all checkpoints.

---

## Checkpoint Enforcement Layers

Each checkpoint is tagged with its enforcement layer:

| Tag | Meaning | Reliability |
|-----|---------|-------------|
| `[code]` | Enforced by Python code paths | **High** — deterministic, testable |
| `[instruction]` | Enforced by skill/instruction files | **Medium** — depends on LLM following rules |
| `[both]` | Has code support + instruction guidance | **High** — defence in depth |

---

## Dimension 1: Self-starting (weight: 15%)

Can the system go from zero state to full operation without human help (beyond initial config)?

| # | Layer | Checkpoint | PASS criteria | Verification procedure |
|---|-------|-----------|---------------|----------------------|
| 1.1 | `[instruction]` | Sentinel detects empty database | `sentinel/business-logic.md` step 3 checks `total feeds == 0` and creates a seed plan | **T1**: `grep -n 'total feeds\|feeds.total.*0\|seed' agents/skills/sentinel/business-logic.md` returns the rule. **T2**: Run sentinel with empty DB; verify seed plan is created. |
| 1.2 | `[code]` | Startup recovers stale plans | `StartupRecoveryMiddleware.after_worker_boot()` calls `recover_stale_plans()` on worker boot | **T1**: `grep -n 'recover_stale_plans' agents/middleware.py` returns the call in `after_worker_boot()`. **T2**: Kill worker mid-execution, restart; verify stale plans are requeued. |
| 1.3 | `[code]` | Startup recovers stale article claims | `StartupRecoveryMiddleware.after_worker_boot()` calls `release_stale_article_claims()` | **T1**: `grep -n 'release_stale_article_claims' agents/middleware.py database/articles.py` returns both. **T2**: Kill worker mid-parse, restart; verify claimed articles are released. |
| 1.4 | `[code]` | Worker restart triggers recovery middleware | `StartupRecoveryMiddleware.after_worker_boot()` runs on every worker start; `handle-worker-restart.md` exists with agent rules | **T1**: Read `news48/core/agents/middleware.py` `after_worker_boot()` — verify recovery calls. Verify `handle-worker-restart.md` exists with ≥5 rules. **T2**: Restart worker while actor is mid-execution; verify recovery runs. |
| 1.5 | `[code]` | Old plans archived on startup | `archive_terminal_plans()` is called by `StartupRecoveryMiddleware.after_worker_boot()` | **T1**: `grep -n 'archive_terminal_plans' agents/middleware.py agents/tools/planner.py` returns both. **T2**: Create >24h-old terminal plans, restart; verify they move to archive. |
| 1.6 | `[code]` | Periodiq scheduler auto-enqueues pipeline tasks | `scheduled_feed_fetch`, `scheduled_download`, `scheduled_parser` actors in `agents/actors.py` have `periodic=cron(...)` decorators | **T1**: `grep -n 'periodic=cron' agents/actors.py` returns all three scheduled actors. **T2**: Start periodiq-scheduler; verify tasks are enqueued on cron. |
| 1.7 | `[code]` | Plan deadlock healing runs every 5 minutes | `heal_plan_deadlocks` actor in `agents/actors.py` has `periodic=cron("*/5 * * * *")` | **T1**: `grep -n 'heal_plan_deadlocks' agents/actors.py` returns the actor with `*/5 * * * *` cron decorator. **T2**: Create a campaign-parent deadlock; verify it is healed within 5 minutes. |

**Dimension score** = (sum of checkpoint values / 7) × 5

---

## Dimension 2: Self-monitoring (weight: 20%)

Can the system observe its own health, detect problems, and report them without human prompting?

| # | Layer | Checkpoint | PASS criteria | Verification procedure |
|---|-------|-----------|---------------|----------------------|
| 2.1 | `[instruction]` | Sentinel gathers system metrics | `sentinel/business-logic.md` step 2 lists evidence commands: `stats --json`, `feeds list --json`, `plans list --json`, `cleanup health --json` | **T1**: Read `sentinel/business-logic.md` step 2; verify all 4 commands are listed. **T2**: Run sentinel; verify all 4 commands appear in logs. |
| 2.2 | `[instruction]` | Rates handle 0/0 as undefined | `thresholds.md` Rate Denominator Semantics says undefined/null, not 0% | **T1**: `grep -n 'undefined\|null\|insufficient' agents/skills/shared/thresholds.md` returns relevant rules. **T2**: Run sentinel on empty system; verify report shows `null` rates. |
| 2.3 | `[instruction]` | Canonical thresholds are single source of truth | `grep` for threshold values (10%, 25%, 100 MB, 500 MB, 10 minutes, 30 minutes) returns hits ONLY in `thresholds.md`. Hits in other files that use threshold values as operational references (not redefining them) are excluded. | **T1**: `grep -rn '10%\|25%\|100 MB\|500 MB' agents/skills/ --include='*.md'`. PASS if only `thresholds.md` has the values. PARTIAL if other files reference values contextually. FAIL if other files independently define different values. |
| 2.4 | `[instruction]` | Fact-check thresholds in canonical table | `thresholds.md` contains rows for fact-check completions (24h) and oldest eligible item | **T1**: `grep -n 'Fact-check\|fact-check' agents/skills/shared/thresholds.md` returns at least 2 rows. |
| 2.5 | `[code]` | Sentinel writes structured report | `write_sentinel_report()` tool exists in `agents/tools/sentinel.py` and writes to `data/monitor/latest-report.json` with status, metrics, alerts, recommendations | **T1**: `grep -n 'def write_sentinel_report\|latest-report' agents/tools/sentinel.py` returns function definition and file path. **T2**: Run sentinel; verify `data/monitor/latest-report.json` is created with all 4 fields. |
| 2.6 | `[both]` | Email only sent for WARNING/CRITICAL when configured | Sentinel has `send_email` tool; `task_context.email_configured` is set by `build_task_context()` in `agents/workers.py`; sentinel instructions gate email to WARNING/CRITICAL | **T1**: Verify `send_email` in `agents/sentinel.py` tools list. Verify `email_configured` in `agents/workers.py` `build_task_context()`. **T2**: Run sentinel with HEALTHY status; verify no email sent. Run with WARNING + email configured; verify email sent. |
| 2.7 | `[instruction]` | Self-healing metrics do not trigger plans | `thresholds.md` Self-Healing Metrics section explicitly lists download and parse backlogs as automated by Dramatiq pipeline actors and must not trigger plan creation | **T1**: `grep -n 'self-healing\|automated\|must not' agents/skills/shared/thresholds.md` returns the section. **T2**: Run sentinel with high download backlog; verify no download-backlog plan created. |
| 2.8 | `[instruction]` | Feed stale threshold triggers plan creation | `thresholds.md` Feed Fetching section requires sentinel to create fetch plan when feeds are stale or articles_today is 0 | **T1**: `grep -n 'Feed Fetching\|MUST.*Create\|fetch plan' agents/skills/shared/thresholds.md` returns the section. **T2**: Run sentinel with stale feeds; verify fetch plan created. |

**Dimension score** = (sum of checkpoint values / 8) × 5

---

## Dimension 3: Self-healing (weight: 25%)

Can the system recover from failures and degraded states without human intervention?

| # | Layer | Checkpoint | PASS criteria | Verification procedure |
|---|-------|-----------|---------------|----------------------|
| 3.1 | `[code]` | Background download loop self-heals backlog | `download_cycle` actor runs every minute via Periodiq, processes up to 100 articles per cycle | **T1**: `grep -n 'download_cycle\|limit=100' agents/actors.py commands/download.py` returns the actor and limit. **T2**: Insert articles with `empty` status; verify they are downloaded automatically. |
| 3.2 | `[code]` | Background parse loop self-heals backlog | `parser_cycle` actor runs every 5 minutes via Periodiq, calls `run_autonomous()` which claims and parses downloaded articles | **T1**: `grep -n 'parser_cycle\|run_autonomous' agents/actors.py agents/parser.py` returns the actor and function. **T2**: Insert downloaded articles; verify they are parsed automatically within 5 minutes. |
| 3.3 | `[code]` | Background feed fetch loop maintains inflow | `feed_fetch_cycle` actor runs every minute via Periodiq, fetches all feeds from database | **T1**: `grep -n 'feed_fetch_cycle\|get_all_feeds' agents/actors.py database/feeds.py` returns the actor and function. **T2**: Add feeds to database; verify they are fetched automatically. |
| 3.4 | `[code]` | Plan deadlock healing runs continuously | `heal_plan_deadlocks` actor normalizes campaign-parent references and auto-completes campaigns whose children are all terminal | **T1**: `grep -n 'heal_plan_deadlocks\|_normalize_plan_for_consistency\|_auto_complete_campaigns' agents/actors.py agents/tools/planner.py` returns the actor and helpers. **T2**: Create a campaign-parent deadlock; verify it is healed on next cron tick. |
| 3.5 | `[instruction]` | Executor retries transient download failures | `run-retry.md` specifies retry for `download-failed` articles with up to 3 attempts per domain | **T1**: Read `run-retry.md`; verify it mentions download-failed retries and 3-attempt limit. **T2**: Inject failed downloads; verify executor retries them. |
| 3.6 | `[instruction]` | Parse failures treated as permanent | `run-retry.md` rule 4 explicitly states: do NOT retry parse-failed articles — they are almost always permanent | **T1**: `grep -n 'NOT retry parse\|permanent\|do not.*re-parse' agents/skills/executor/run-retry.md` returns the rule. **T2**: Inject parse-failed articles; verify they are skipped, not retried. |
| 3.7 | `[instruction]` | Domain failure escalation | `run-retry.md` Consecutive Failure Tracking: executor skips domain after 3 failures in same plan; notes feed health investigation needed | **T1**: Read `run-retry.md` Consecutive Failure Tracking section; verify 3-failure skip rule and feed-health escalation note. **T2**: Fail domain 3 times in one plan; verify skip + feed-health note. |
| 3.8 | `[both]` | Wave partial failure isolation | `run-waves.md` checks per-PID exit codes; only failed step is marked failed, others continue | **T1**: Read `run-waves.md` Wave Execution section; verify per-PID exit code checking and partial failure rule. **T2**: In 4-process wave, make 1 fail; verify only it is marked failed. |

**Dimension score** = (sum of checkpoint values / 8) × 5

---

## Dimension 4: Self-scaling (weight: 10%)

Can the system adapt its resource usage to changing workload?

| # | Layer | Checkpoint | PASS criteria | Verification procedure |
|---|-------|-----------|---------------|----------------------|
| 4.1 | `[instruction]` | Wave parallelism for fetch/download | `run-waves.md` specifies parallel waves of at most 4 processes using `&` + `wait` | **T1**: `grep -n 'at most 4\|background\|wait' agents/skills/executor/run-waves.md` returns parallelism rules. **T2**: Create multi-domain plan; verify parallel execution in logs. |
| 4.2 | `[code]` | Executor concurrent instances | Dramatiq worker `--threads 8` allows multiple concurrent executor actors | **T1**: `grep -n 'threads' docker-compose.yml` returns `--threads 8`. **T2**: Create 5 eligible plans; verify 5 executor actors run concurrently. |
| 4.3 | `[code]` | Parser concurrent instances | Dramatiq worker `--threads 8` allows multiple concurrent parser actors | **T1**: `grep -n 'threads' docker-compose.yml` returns `--threads 8`. **T2**: Queue multiple downloaded articles; verify concurrent parsing. |
| 4.4 | `[code]` | Fact-checker concurrent instances | Dramatiq worker `--threads 8` allows multiple concurrent fact-checker actors | **T1**: `grep -n 'threads' docker-compose.yml` returns `--threads 8`. **T2**: Queue multiple fact-unchecked articles; verify concurrent fact-checking. |
| 4.5 | `[instruction]` | Batch limits respected and repeated | `run-command.md` specifies using `--limit` and repeating commands until backlog cleared or stalled | **T1**: `grep -n 'limit\|repeat\|stalled' agents/skills/executor/run-command.md` returns batch rules. **T2**: Create plan with large backlog; verify repeated command calls with --limit. |

**Dimension score** = (sum of checkpoint values / 5) × 5

---

## Dimension 5: Self-optimizing (weight: 10%)

Can the system improve its own performance based on historical data?

| # | Layer | Checkpoint | PASS criteria | Verification procedure |
|---|-------|-----------|---------------|----------------------|
| 5.1 | `[instruction]` | Lessons learned persisted across runs | `lessons-learned.md` specifies aggressive lesson saving; `save_lesson` tool persists knowledge; lessons are loaded into agent prompts at startup | **T1**: `grep -n 'save_lesson\|aggressively\|memory' agents/skills/shared/lessons-learned.md` returns the rules. Verify `save_lesson` in agent tool lists. **T2**: Run executor; verify lessons are loaded and new lessons are saved. |
| 5.2 | `[code]` | Sentinel receives backlog context | `agents/workers.py` `build_task_context()` sets `backlog_high=True` when download or parse backlog exceeds 200 | **T1**: `grep -n 'backlog_high\|backlog.*200' agents/workers.py` returns the context building logic. **T2**: Create backlog >200; verify sentinel receives `backlog_high: true`. |
| 5.3 | `[instruction]` | Feed curation removes underperforming feeds | `feed-curation.md` specifies deletion rules: 3+ consecutive empty fetch cycles, >80% download failure, >60% parse failure, >50% negative fact-check | **T1**: Read `feed-curation.md`; verify all 4 deletion rules and safety limits. **T2**: Create a feed with >80% download failure; verify sentinel deletes it. |
| 5.4 | `[instruction]` | Sentinel deduplicates plans before creation | `sentinel/business-logic.md` step 6 requires checking `news48 plans list --json` first to avoid duplicating existing pending plans | **T1**: `grep -n 'plans list\|duplicate\|existing' agents/skills/sentinel/business-logic.md` returns the deduplication rule. **T2**: With active pending plan for a scope, run sentinel; verify no duplicate created. |

**Dimension score** = (sum of checkpoint values / 4) × 5

---

## Dimension 6: Error containment (weight: 20%)

Can the system prevent errors from cascading and maintain stability?

| # | Layer | Checkpoint | PASS criteria | Verification procedure |
|---|-------|-----------|---------------|----------------------|
| 6.1 | `[instruction]` | Unified error taxonomy | `error-taxonomy.md` defines structured codes with `category.detail` format; `enforce-quality.md` references the taxonomy for failure codes | **T1**: Verify `error-taxonomy.md` has ≥10 codes. `grep -n 'error-taxonomy\|error.taxonomy' agents/skills/parser/enforce-quality.md` shows it references the taxonomy. `grep -rn 'quality_gate\.\|normalization\.' agents/skills/` returns 0 results (no non-canonical codes). |
| 6.2 | `[instruction]` | Fail-safely rules enforced | `fail-safely.md` contains a rule about breaking loops after 5 repeated tool errors with same signature | **T1**: `grep -n '5 repeated\|break.*loop\|same signature' agents/skills/shared/fail-safely.md` returns the rule. **T2**: Trigger 5 repeated tool errors; verify agent breaks loop. |
| 6.3 | `[instruction]` | Retry limits enforced | `fail-safely.md` rule 2 limits retries to never more than twice for same failed action; `run-retry.md` enforces 3-attempt domain limit | **T1**: `grep -n 'retry.*twice\|more than twice\|never retry' agents/skills/shared/fail-safely.md` returns the rule. `grep -n '3 attempts\|3/3' agents/skills/executor/run-retry.md` returns the domain limit. |
| 6.4 | `[both]` | Wave failure isolation | `run-waves.md` checks per-PID exit codes; failed process does not fail entire plan | **T1**: Read `run-waves.md` lines 14-38; verify per-PID checking and isolation rule. **T2**: Make 1 of 4 wave members fail; verify others complete and only failed one is marked. |
| 6.5 | `[instruction]` | Fact-check eligibility gated | `run-fact-check.md` rule 2 limits fact-checking to `fact-unchecked` articles only; lists ineligible statuses | **T1**: `grep -n 'fact-unchecked\|ineligible\|not eligible' agents/skills/executor/run-fact-check.md` returns the gating rule. **T2**: Attempt to fact-check a `downloaded` article; verify rejection. |
| 6.6 | `[instruction]` | Quality gate blocks bad output | `enforce-quality.md` specifies minimum content length (1200 chars standard, 400 chars absolute minimum) and uses canonical error codes from `error-taxonomy.md` | **T1**: `grep -n 'out_of_bounds\|1200.*char\|400.*char' agents/skills/parser/enforce-quality.md` returns quality rules. **T2**: Submit article with 200-char content; verify `parse.out_of_bounds` failure. |
| 6.7 | `[instruction]` | No inter-skill cross-references | Skill files do not reference other skills by name (business-logic routing tables and shared canonical references excluded) | **T1**: `grep -rn 'loaded in this prompt\|see the.*skill\|see the.*procedure loaded\|refer to\|described in\|defined in\|documented in' agents/skills/ --include='*.md'` returns 0 results. References to `shared/error-taxonomy.md` or `shared/thresholds.md` as canonical sources are excluded. |
| 6.8 | `[code]` | Runtime timeout enforcement | `time_limit` in `@dramatiq.actor()` decorator per actor (e.g., `time_limit=10 * 60 * 1000` for 10 min) | **T1**: `grep -n 'time_limit' agents/actors.py` returns the timeout settings per actor. **T2**: Run an actor that exceeds time_limit; verify Dramatiq terminates it. |

**Dimension score** = (sum of checkpoint values / 8) × 5

---

## Overall Score Calculation

```
Overall = (Self-starting × 0.15)
        + (Self-monitoring × 0.20)
        + (Self-healing × 0.25)
        + (Self-scaling × 0.10)
        + (Self-optimizing × 0.10)
        + (Error containment × 0.20)
```

The weights reflect operational importance: self-healing and self-monitoring are weighted highest because they most directly reduce human intervention.

### Score Interpretation

| Score | Level | Meaning |
|-------|-------|---------|
| 4.5 – 5.0 | **Autonomous** | System runs unattended for extended periods. Human involvement only for strategic decisions. |
| 3.5 – 4.4 | **Supervised** | System runs autonomously under normal conditions. Human oversight needed for edge cases and degradation. |
| 2.5 – 3.4 | **Assisted** | System handles happy path but requires human intervention for failures, scaling, and recovery. |
| 1.5 – 2.4 | **Manual** | System needs frequent human input. Most error recovery and optimization is manual. |
| 1.0 – 1.4 | **Prototype** | System runs only with direct human supervision. |

---

## v4 Architecture Improvements Over v3

The v4 architecture replaces the monolithic orchestrator with **Dramatiq workers** and **Periodiq scheduling**:

| Capability | v3 Enforcement | v4 Enforcement | Impact |
|-----------|---------------|---------------|--------|
| Scheduling | Tick-based loop (old orchestrator) | Periodiq cron decorators in `agents/actors.py` | No polling overhead, precise cron scheduling |
| Execution | `fork_agent()` subprocess spawning (old) | Dramatiq in-process actors | Faster startup, shared memory, no PID management |
| State management | File-based JSON state + PID file (old) | Redis message broker + Dramatiq middleware | Distributed, crash-safe, no file locking |
| Recovery | Manual recovery on daemon startup (old) | `StartupRecoveryMiddleware.after_worker_boot()` | Automatic on every worker restart |
| Plan ownership | PID-based (`pid:12345`) | Message-based (`executor:dramatiq-<id>`) | Reliable failure detection, no stale PIDs |
| Agent concurrency | `max_concurrent` via `fork_agent()` limits | Dramatiq `--threads N` worker config | Simpler scaling, no subprocess overhead |
| Observability | `agents dashboard` reading log files | Dozzle + RedisInsight | Standard Docker tooling, no custom dashboard |

---

## Calibration Examples

These examples show how to score borderline cases consistently.

### Example A: Threshold reference vs duplication (checkpoint 2.3)

`run-feed-health.md:8` says: *"Identify stale feeds: `last_fetched_at` beyond the configured threshold (see thresholds skill)."*

- This references the threshold without embedding the value.
- If `thresholds.md` changed the feed-stale warning from 10 to 15 minutes, `run-feed-health.md` would remain correct.
- **Ruling: PASS** — the value is not embedded; the reference is to the canonical source.

### Example B: LLM-dependent loop breaking (checkpoint 6.2)

`fail-safely.md:5` says: *"Break loops after 5 repeated tool errors with the same signature."*

- The rule is clear and unambiguous in the instruction.
- However, "same signature" detection depends on LLM pattern recognition — not code-enforced.
- **Ruling: PASS** — the instruction is clear and complete. The `[instruction]` tag already signals LLM-dependence. Score reductions for enforcement layer are handled by the tagging system, not by downgrading individual checkpoint scores.

### Example C: Code function exists but never called (hypothetical)

A hypothetical function `_auto_scale_workers()` exists in a module but is never called from any entry point.

- The code exists but has no effect at runtime.
- **Ruling: FAIL** — code must be both present and reachable. Dead code is not a capability.

### Example D: Periodiq-scheduled actor with fixed cron (checkpoint 3.1)

`download_cycle` actor is enqueued every minute by `scheduled_download` via `periodic=cron("* * * * *")`.

- The actor runs automatically on a fixed cron schedule managed by Periodiq.
- The interval is not dynamically adjustable, but the actor is code-enforced and always active.
- **Ruling: PASS** — the capability exists and is reachable. Lack of dynamic tuning is captured in Dimension 5 (self-optimizing), not here.

---

## Per-Checkpoint Assessment Log

After scoring, record per-checkpoint results in `.scoring/latest-assessment.json`:

```json
{
  "date": "2026-04-15",
  "assessor": "architect-mode",
  "architecture": "v4",
  "tier": "T1",
  "checkpoints": {
    "1.1": {"result": "PASS", "value": 1.0, "evidence": "sentinel/business-logic.md step 2 — checks total feeds == 0, creates seed plan"},
    "1.2": {"result": "PASS", "value": 1.0, "evidence": "agents/middleware.py — StartupRecoveryMiddleware.after_worker_boot() calls recover_stale_plans() on every worker start"},
    "2.3": {"result": "PARTIAL", "value": 0.5, "evidence": "run-feed-health.md:8 references threshold without embedding value, but another file embeds a value"}
  },
  "dimensions": {
    "self_starting": {"score": 5.0, "pass": 7, "partial": 0, "fail": 0},
    "self_monitoring": {"score": 4.7, "pass": 7, "partial": 1, "fail": 0},
    "self_healing": {"score": 5.0, "pass": 8, "partial": 0, "fail": 0},
    "self_scaling": {"score": 5.0, "pass": 5, "partial": 0, "fail": 0},
    "self_optimizing": {"score": 5.0, "pass": 4, "partial": 0, "fail": 0},
    "error_containment": {"score": 5.0, "pass": 8, "partial": 0, "fail": 0}
  },
  "overall": 4.9
}
```

This makes scoring differences traceable between assessments. When scores change, diff the JSON to identify which specific checkpoints moved.

---

## Score History

Record each assessment here for trend tracking.

| Date | Self-start | Self-monitor | Self-heal | Self-scale | Self-optimize | Error contain | **Overall** | Architecture | Notes |
|------|-----------|-------------|----------|-----------|--------------|--------------|-------------|-------------|-------|
| 2026-04-12 | 4.0 | 3.0 | 3.0 | 2.0 | 2.0 | 4.0 | **3.0** | v2 | Pre-fix baseline |
| 2026-04-12 | 4.5 | 4.5 | 4.0 | 2.5 | 3.0 | 4.5 | **4.0** | v2 | All critical/high fixes applied |
| 2026-04-12 | 5.0 | 4.7 | 5.0 | 3.75 | 3.75 | 5.0 | **4.7** | v2 | Strict scoring; 4.4+5.4 FAIL; 2.3 PARTIAL |
| 2026-04-15 | 5.0 | 5.0 | 5.0 | 5.0 | 5.0 | 5.0 | **5.0** | v3 | T1 only; all 40 checkpoints PASS; code-enforced loops + concurrency replace instruction-only v2 gaps |
| 2026-04-22 | 5.0 | 5.0 | 5.0 | 5.0 | 5.0 | 5.0 | **5.0** | v4 | Dramatiq migration complete; orchestrator removed; Periodiq + Redis replace scheduling |
| 2026-04-26 | 5.0 | 4.7 | 5.0 | 5.0 | 5.0 | 5.0 | **4.9** | v4 | T1 deep review; 2.4 fixed (added missing fact-check threshold rows to thresholds.md); 2.6 PARTIAL (email gating not explicit WARNING/CRITICAL); doc corrections: step numbers, cron frequencies, content lengths, calibration example D updated for v4 |
| | | | | | | | | | |
