# Autonomous Operation Score — Measurement Guide

A repeatable methodology for scoring how well news48 operates without human intervention.

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
| 1.1 | `[instruction]` | Bootstrap detects empty database | `begin-planning-cycle.md` contains a rule that checks `feeds.total == 0` and runs `news48 seed` | **T1**: `grep -n 'feeds.total.*0\|seed' agents/skills/planner/begin-planning-cycle.md` returns the rule. **T2**: Run planner with empty DB; verify seed command executes. |
| 1.2 | `[instruction]` | Bootstrap failure creates remediation plan | `begin-planning-cycle.md` contains a rule that creates a `discovery` remediation plan when seed fails, and does NOT loop | **T1**: `grep -n 'discovery\|remediation\|do NOT loop' agents/skills/planner/begin-planning-cycle.md` returns the rule. **T2**: Remove `seed.txt`, run planner; verify no loop and a discovery plan is created. |
| 1.3 | `[code]` | Startup recovers stale plans | `_recover_stale_plans()` exists in `orchestrator.py` and is called during daemon startup | **T1**: `grep -n '_recover_stale_plans' agents/orchestrator.py` returns both the definition and the call site. **T2**: Kill orchestrator mid-execution, restart; verify stale plans are requeued. |
| 1.4 | `[code]` | Startup recovers stale article claims | `_recover_stale_articles()` exists in `orchestrator.py` and calls `release_stale_article_claims()` | **T1**: `grep -n '_recover_stale_articles\|release_stale_article_claims' agents/orchestrator.py database/articles.py` returns both. **T2**: Kill orchestrator mid-parse, restart; verify claimed articles are released. |
| 1.5 | `[code]` | Orchestrator restart doesn't kill running agents | `load_state()` re-attaches to still-alive PIDs; `handle-orchestrator-restart.md` exists | **T1**: Read `orchestrator.py` `load_state()` — verify PIL re-attachment logic. Verify `handle-orchestrator-restart.md` exists. **T2**: Restart orchestrator while agent is alive; verify agent completes. |
| 1.6 | `[code]` | Old plans are archived on startup | `_archive_old_plans()` exists and is called during daemon startup | **T1**: `grep -n '_archive_old_plans\|archive_terminal_plans' agents/orchestrator.py agents/tools/planner.py` returns both. **T2**: Create >24h-old terminal plans, restart; verify they move to `.plans/archive/`. |

**Dimension score** = (sum of checkpoint values / 6) × 5

---

## Dimension 2: Self-monitoring (weight: 20%)

Can the system observe its own health, detect problems, and report them without human prompting?

| # | Layer | Checkpoint | PASS criteria | Verification procedure |
|---|-------|-----------|---------------|----------------------|
| 2.1 | `[instruction]` | Monitor gathers all 7 evidence commands | `begin-monitoring-cycle.md` Step 1 lists exactly 7 CLI commands | **T1**: Read `begin-monitoring-cycle.md` lines 9-17; count exactly 7 numbered commands. **T2**: Run monitor; verify all 7 commands appear in logs. |
| 2.2 | `[instruction]` | Rates handle 0/0 as undefined | `begin-monitoring-cycle.md` Step 2 and `thresholds.md` Rate Denominator Semantics say undefined/null, not 0% | **T1**: `grep -n 'undefined\|null\|insufficient' agents/skills/monitor/begin-monitoring-cycle.md agents/skills/shared/thresholds.md` returns relevant rules. **T2**: Run monitor on empty system; verify report shows `null` rates. |
| 2.3 | `[instruction]` | Canonical thresholds are single source of truth | `grep` for threshold values (10%, 25%, 7 days, 14 days, 100 MB, 500 MB, 50, 200) returns hits ONLY in `thresholds.md`. Hits in other files that use threshold values as operational inputs (not redefining them) are excluded. | **T1**: `grep -rn '10%\|25%\|100 MB\|500 MB\|7 days\|14 days' agents/skills/ --include='*.md'`. PASS if only `thresholds.md` has the values. PARTIAL if other files reference values contextually (e.g., "beyond 7 days threshold"). FAIL if other files independently define different values. |
| 2.4 | `[instruction]` | Fact-check thresholds are in canonical table | `thresholds.md` contains rows for fact-check completions (24h) and oldest eligible item | **T1**: `grep -n 'Fact-check' agents/skills/shared/thresholds.md` returns at least 2 rows. |
| 2.5 | `[instruction]` | Disk space is monitored | `check-disk-space.md` exists and specifies `/tmp` and project directory monitoring | **T1**: Read `check-disk-space.md`; verify it mentions `/tmp`, `.`, and specifies thresholds. **T2**: Run monitor; verify `disk_space` in report metrics. |
| 2.6 | `[instruction]` | Stale monitor report detected by planner | `begin-planning-cycle.md` contains a rule about report timestamp staleness (>2x monitor interval) | **T1**: `grep -n 'stale\|older than\|2x\|outdated' agents/skills/planner/begin-planning-cycle.md` returns the staleness check rule. **T2**: Set report timestamp >20 min old; run planner; verify staleness is noted. |
| 2.7 | `[instruction]` | Email only sent for WARNING/CRITICAL + configured | `send-email.md` scope gates to WARNING/CRITICAL; decision table shows HEALTHY = "Do not send" | **T1**: Read `send-email.md`; verify scope line, decision table, and HEALTHY row. **T2**: Run monitor with HEALTHY status; verify no email. |
| 2.8 | `[instruction]` | Email pre-flight checks configuration | `send-email.md` has a Pre-flight Check section that verifies `email_configured` before sending | **T1**: `grep -n 'pre-flight\|email_configured' agents/skills/monitor/send-email.md` returns both. **T2**: Run monitor with WARNING + email NOT configured; verify skip with note, not error. |

**Dimension score** = (sum of checkpoint values / 8) × 5

---

## Dimension 3: Self-healing (weight: 25%)

Can the system recover from failures and degraded states without human intervention?

| # | Layer | Checkpoint | PASS criteria | Verification procedure |
|---|-------|-----------|---------------|----------------------|
| 3.1 | `[instruction]` | Executor feedback loop to planner | `verify-plan.md` writes to `.plans/feedback/` on INVALID conditions; `build-plan.md` reads `.plans/feedback/` before creating plans | **T1**: `grep -n 'feedback' agents/skills/executor/verify-plan.md agents/skills/planner/build-plan.md` returns write + read rules. **T2**: Create plan with invalid condition; verify feedback file written and planner reads it. |
| 3.2 | `[instruction]` | Retry plans created for failures | `plan-retry.md` exists and specifies retry for `download-failed` and `parse-failed` | **T1**: Read `plan-retry.md`; verify it mentions both failure statuses and retry limits. **T2**: Inject failed articles; verify planner creates retry plan. |
| 3.3 | `[instruction]` | Parse retries delegated to Parser | `run-retry.md` specifies creating child parse plans, NOT re-parsing directly | **T1**: `grep -n 'child parse plan\|do not.*re-parse\|Parser agent' agents/skills/executor/run-retry.md` returns delegation rule. |
| 3.4 | `[instruction]` | Domain failure escalation | `run-retry.md` Consecutive Failure Tracking section: executor skips after 3 within-plan failures; planner escalates to `feed-health` | **T1**: Read `run-retry.md` lines 14-18; verify 3-failure skip rule and planner escalation description. **T2**: Fail domain 3 times in one plan; verify skip + feed-health escalation. |
| 3.5 | `[instruction]` | Permanently unreachable feed detection | `handle-unreachable-feeds.md` detects 30+ day stale feeds and creates `discovery` remediation plan | **T1**: Read `handle-unreachable-feeds.md`; verify 30-day rule, recovery attempt, and remediation plan creation. |
| 3.6 | `[instruction]` | Stuck plan remediation | `remediate-stuck.md` triggers on `requeue_count >= 2` and creates investigation plan | **T1**: `grep -n 'requeue_count' agents/skills/planner/remediate-stuck.md` returns trigger rule. |
| 3.7 | `[both]` | Wave partial failure handling | `run-waves.md` checks per-PID exit codes; only failed step is marked failed, others continue | **T1**: Read `run-waves.md` Wave Execution section; verify per-PID exit code checking and partial failure rule. **T2**: In 4-process wave, make 1 fail; verify only it is marked failed. |
| 3.8 | `[code]` | Plan corruption repair | `plans remediate --apply` command exists in `commands/plans.py`; `_remediate_plan()` function repairs corruption | **T1**: `grep -n 'def _remediate_plan\|remediate' commands/plans.py` returns function + command. **T2**: Corrupt a plan's parent chain; run `plans remediate --apply --json`; verify repair. |

**Dimension score** = (sum of checkpoint values / 8) × 5

---

## Dimension 4: Self-scaling (weight: 10%)

Can the system adapt its resource usage to changing workload?

| # | Layer | Checkpoint | PASS criteria | Verification procedure |
|---|-------|-----------|---------------|----------------------|
| 4.1 | `[instruction]` | Wave parallelism for fetch/download | `run-waves.md` specifies parallel waves of up to 4 processes using `&` + `wait` | **T1**: `grep -n 'at most 4\|background\|wait' agents/skills/executor/run-waves.md` returns parallelism rules. **T2**: Create multi-domain plan; verify parallel execution in logs. |
| 4.2 | `[instruction]` | Throughput emergency priority override | `prioritize-goals.md` Throughput Emergency Override section defers goals 4-9 when backlog >200 and non-improving | **T1**: Read `prioritize-goals.md` lines 28-32; verify override section with goal 1-3 focus and 4-9 deferral. |
| 4.3 | `[instruction]` | Batch limits respected and repeated | `run-command.md` specifies using `--limit` and repeating commands until backlog cleared or stalled | **T1**: `grep -n 'limit\|repeat' agents/skills/executor/run-command.md` returns batch rules (lines 6, 17). **T2**: Create plan with large backlog; verify repeated command calls with --limit. |
| 4.4 | `[code]` | Dynamic concurrency adjustment | Python code in orchestrator or tools adjusts wave size or intervals based on system load at runtime | **T1**: `grep -rn 'dynamic.*concurren\|adjust.*wave\|load.*adjust' agents/ --include='*.py'` returns adjustment logic. FAIL if 0 results. **T2**: Run under varying load; verify wave size changes. |

**Dimension score** = (sum of checkpoint values / 4) × 5

> **Note:** Checkpoint 4.4 requires runtime code changes (not instruction-layer). Expected to score 0 until implemented.

---

## Dimension 5: Self-optimizing (weight: 10%)

Can the system improve its own performance based on historical data?

| # | Layer | Checkpoint | PASS criteria | Verification procedure |
|---|-------|-----------|---------------|----------------------|
| 5.1 | `[instruction]` | Metrics history persisted | `write-metrics-history.md` specifies writing timestamped `.metrics/<timestamp>.json` files | **T1**: Read `write-metrics-history.md`; verify mkdir, timestamped filename, required JSON keys. **T2**: Run monitor; verify `.metrics/*.json` file created. |
| 5.2 | `[instruction]` | Historical backlog comparison works | `throughput-emergency.md` Historical Comparison Procedure reads `.metrics/` and compares across cycles | **T1**: Read `throughput-emergency.md` lines 22-34; verify read, compare, and non-improving definition. |
| 5.3 | `[instruction]` | Throughput emergency activates and deactivates | `throughput-emergency.md` has both trigger conditions (>200 + non-improving) and exit condition (both clear for one full cycle) | **T1**: `grep -n 'Trigger\|Exit' agents/skills/planner/throughput-emergency.md` returns both sections. **T2**: Trigger emergency; verify activation. Clear backlog; verify deactivation. |
| 5.4 | `[code]` | Adaptive interval tuning | Python code adjusts scheduling intervals based on observed throughput | **T1**: `grep -rn 'adaptive\|adjust.*interval\|tune.*schedule' agents/ --include='*.py'` returns tuning logic. FAIL if 0 results. **T2**: Run over multiple cycles; verify interval changes. |

**Dimension score** = (sum of checkpoint values / 4) × 5

> **Note:** Checkpoint 5.4 requires runtime code changes. Expected to score 0 until implemented.

---

## Dimension 6: Error containment (weight: 20%)

Can the system prevent errors from cascading and maintain stability?

| # | Layer | Checkpoint | PASS criteria | Verification procedure |
|---|-------|-----------|---------------|----------------------|
| 6.1 | `[instruction]` | Unified error taxonomy | `error-taxonomy.md` defines structured codes; `enforce-quality.md` references the taxonomy for failure codes | **T1**: Verify `error-taxonomy.md` has ≥10 codes. `grep -n 'error-taxonomy\|error.taxonomy' agents/skills/parser/enforce-quality.md` shows it references the taxonomy. `grep -rn 'quality_gate\.\|normalization\.' agents/skills/` returns 0 results (no non-canonical codes). |
| 6.2 | `[instruction]` | Fail-safely rules enforced | `fail-safely.md` contains a rule about breaking loops after 5 repeated tool errors with same signature | **T1**: `grep -n '5 repeated\|break.*loop\|same signature' agents/skills/shared/fail-safely.md` returns the rule. **T2**: Trigger 5 repeated tool errors; verify agent breaks loop. |
| 6.3 | `[instruction]` | Retry limits enforced | `fail-safely.md` contains a rule limiting retries (never more than twice for same failed action) | **T1**: `grep -n 'retry.*twice\|more than twice\|never retry' agents/skills/shared/fail-safely.md` returns the rule. **T2**: Retry failed action 3 times; verify agent stops. |
| 6.4 | `[both]` | Wave failure isolation | `run-waves.md` checks per-PID exit codes; failed process doesn't fail entire plan | **T1**: Read `run-waves.md` lines 14-38; verify per-PID checking and isolation rule. **T2**: Make 1 of 4 wave members fail; verify others complete and only failed one is marked. |
| 6.5 | `[instruction]` | Fact-check eligibility gated | `run-fact-check.md` Rule 2 limits fact-checking to `fact-unchecked` articles only; lists ineligible statuses | **T1**: `grep -n 'fact-unchecked\|ineligible\|not eligible' agents/skills/executor/run-fact-check.md` returns the gating rule. **T2**: Attempt to fact-check a `downloaded` article; verify rejection. |
| 6.6 | `[instruction]` | Plan deduplication prevents duplicate work | `deduplicate-plans.md` requires checking existing plans before creating new ones; one plan per concern | **T1**: Read `deduplicate-plans.md`; verify `list_plans` check rule and "one plan per concern" rule. **T2**: With active plan for scope, run planner; verify no duplicate created. |
| 6.7 | `[instruction]` | Quality gate blocks bad output | `enforce-quality.md` specifies minimum content length (200 chars absolute minimum) and uses `parse.out_of_bounds` code | **T1**: `grep -n 'out_of_bounds\|200.*char\|600.*char' agents/skills/parser/enforce-quality.md` returns quality rules. **T2**: Submit article with 100-char content; verify `parse.out_of_bounds` failure. |
| 6.8 | `[instruction]` | No inter-skill cross-references | Skill files do not reference other skills by name (business-logic routing tables and shared canonical references excluded) | **T1**: `grep -rn 'loaded in this prompt\|see the.*skill\|see the.*procedure loaded\|refer to\|described in\|defined in\|documented in' agents/skills/ --include='*.md'` returns 0 results. References to `shared/error-taxonomy.md` or `shared/thresholds.md` as canonical sources are excluded. |

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

## Calibration Examples

These examples show how to score borderline cases consistently.

### Example A: Threshold reference vs duplication (checkpoint 2.3)

`run-feed-health.md:8` says: *"Identify stale feeds: `last_fetched_at` beyond 7 days threshold."*

- This embeds the value "7 days" even though it frames it as a "threshold" reference.
- If `thresholds.md` changed "Feed stale" from 7 to 10 days, `run-feed-health.md` would become stale.
- **Ruling: PARTIAL** — the value is embedded even if contextually referenced. A PASS requires saying "beyond the feed-stale warning threshold" without embedding the number.

### Example B: LLM-dependent loop breaking (checkpoint 6.2)

`fail-safely.md:5` says: *"Break loops after 5 repeated tool errors with the same signature."*

- The rule is clear and unambiguous in the instruction.
- However, "same signature" detection depends on LLM pattern recognition — not code-enforced.
- **Ruling: PASS** — the instruction is clear and complete. The `[instruction]` tag already signals LLM-dependence. Score reductions for enforcement layer are handled by the tagging system, not by downgrading individual checkpoint scores.

### Example C: Code function exists but never called (hypothetical)

A function `_auto_scale_workers()` exists in `orchestrator.py` but is never called from `daemon_loop()`.

- The code exists but has no effect at runtime.
- **Ruling: FAIL** — code must be both present and reachable. Dead code is not a capability.

---

## Per-Checkpoint Assessment Log

After scoring, record per-checkpoint results in `.scoring/latest-assessment.json`:

```json
{
  "date": "2026-04-12",
  "assessor": "architect-mode",
  "tier": "T1",
  "checkpoints": {
    "1.1": {"result": "PASS", "value": 1.0, "evidence": "begin-planning-cycle.md:5 — rule checks feeds.total == 0"},
    "1.2": {"result": "PASS", "value": 1.0, "evidence": "begin-planning-cycle.md:8 — creates discovery remediation plan"},
    "2.3": {"result": "PARTIAL", "value": 0.5, "evidence": "run-feed-health.md:8 embeds '7 days' value"},
    "4.4": {"result": "FAIL", "value": 0.0, "evidence": "grep returns 0 results — no runtime code"}
  },
  "dimensions": {
    "self_starting": {"score": 5.0, "pass": 6, "partial": 0, "fail": 0},
    "self_monitoring": {"score": 4.7, "pass": 7, "partial": 1, "fail": 0},
    "self_healing": {"score": 5.0, "pass": 8, "partial": 0, "fail": 0},
    "self_scaling": {"score": 3.75, "pass": 3, "partial": 0, "fail": 1},
    "self_optimizing": {"score": 3.75, "pass": 3, "partial": 0, "fail": 1},
    "error_containment": {"score": 5.0, "pass": 8, "partial": 0, "fail": 0}
  },
  "overall": 4.7
}
```

This makes scoring differences traceable between assessments. When scores change, diff the JSON to identify which specific checkpoints moved.

---

## Score History

Record each assessment here for trend tracking.

| Date | Self-start | Self-monitor | Self-heal | Self-scale | Self-optimize | Error contain | **Overall** | Notes |
|------|-----------|-------------|----------|-----------|--------------|--------------|-------------|-------|
| 2026-04-12 (original) | 4.0 | 3.0 | 3.0 | 2.0 | 2.0 | 4.0 | **3.0** | Pre-fix baseline |
| 2026-04-12 (post-fix) | 4.5 | 4.5 | 4.0 | 2.5 | 3.0 | 4.5 | **4.0** | All critical/high fixes applied |
| 2026-04-12 (reassess) | 5.0 | 4.7 | 5.0 | 3.75 | 3.75 | 5.0 | **4.7** | Strict checkpoint scoring; 4.4+5.4 remain FAIL (no runtime code); 2.3 PARTIAL |
| | | | | | | | | |
