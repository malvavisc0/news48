# Autonomous Operation Score — Measurement Guide

A repeatable methodology for scoring how well news48 operates without human intervention.

---

## How to Use This Document

1. Walk through each of the 6 dimensions below.
2. For every checkpoint, verify the claim against the current codebase and a live system run.
3. Record PASS / FAIL / PARTIAL for each checkpoint.
4. Compute the dimension score using the formula in each section.
5. Compute the overall score using the weighted formula at the bottom.
6. Record the date, scores, and notes in the **Score History** table.

---

## Dimension 1: Self-starting (weight: 15%)

Can the system go from zero state to full operation without human help (beyond initial config)?

| # | Checkpoint | How to verify | Score |
|---|-----------|--------------|-------|
| 1.1 | Bootstrap detects empty database | Run with empty DB. Planner must detect `feeds.total == 0` and seed automatically. | 0 or 1 |
| 1.2 | Bootstrap failure creates remediation plan | Remove `seed.txt` and run. Planner must NOT loop — must create a `discovery` remediation plan. | 0 or 1 |
| 1.3 | Startup recovers stale plans | Kill orchestrator mid-execution, restart. Stale `executing` plans must be requeued. | 0 or 1 |
| 1.4 | Startup recovers stale article claims | Kill orchestrator mid-parse, restart. Articles stuck in `processing_status: claimed` must be released. | 0 or 1 |
| 1.5 | Orchestrator restart doesn't kill running agents | Restart orchestrator while agent subprocess is alive. Agent must complete; orchestrator re-attaches. | 0 or 1 |
| 1.6 | Old plans are archived on startup | Restart with >24h-old terminal plans. They must move to `.plans/archive/`. | 0 or 1 |

**Dimension score** = (sum of checkpoints / 6) × 5

---

## Dimension 2: Self-monitoring (weight: 20%)

Can the system observe its own health, detect problems, and report them without human prompting?

| # | Checkpoint | How to verify | Score |
|---|-----------|--------------|-------|
| 2.1 | Monitor gathers all 7 evidence commands | Read `begin-monitoring-cycle.md` Step 1. Run monitor; confirm all 7 commands execute. | 0 or 1 |
| 2.2 | Rates handle 0/0 as undefined | Run on empty system. Monitor report must show `null` rates, not `0%`. | 0 or 1 |
| 2.3 | Canonical thresholds are single source of truth | Verify no skill file duplicates threshold values. Only `thresholds.md` defines them. | 0 or 1 |
| 2.4 | Fact-check thresholds are in canonical table | `thresholds.md` must include fact-check rows (completions 24h + oldest eligible item). | 0 or 1 |
| 2.5 | Disk space is monitored | Monitor report must include `disk_space` metrics with `/tmp` and project directory usage. | 0 or 1 |
| 2.6 | Stale monitor report detected by planner | Set report timestamp >20 min old. Planner must note staleness and gather own evidence. | 0 or 1 |
| 2.7 | Email only sent for WARNING/CRITICAL + configured | Run monitor with HEALTHY status. No email. Run with WARNING + email configured. Email sent. | 0 or 1 |
| 2.8 | Email pre-flight checks configuration | Run monitor with email NOT configured + WARNING. Must skip email with note, not error. | 0 or 1 |

**Dimension score** = (sum of checkpoints / 8) × 5

---

## Dimension 3: Self-healing (weight: 25%)

Can the system recover from failures and degraded states without human intervention?

| # | Checkpoint | How to verify | Score |
|---|-----------|--------------|-------|
| 3.1 | Executor feedback loop to planner | Create a plan with an invalid condition. Executor must write `.plans/feedback/`. Planner must read and revise. | 0 or 1 |
| 3.2 | Retry plans created for failures | Inject `download-failed` articles. Planner must create retry plan. Executor must retry downloads. | 0 or 1 |
| 3.3 | Parse retries delegated to Parser | Executor must create child parse plans for `parse-failed` articles, NOT re-parse directly. | 0 or 1 |
| 3.4 | Domain failure escalation | Fail a domain 3 times in one retry plan. Executor must skip it and planner must escalate to `feed-health`. | 0 or 1 |
| 3.5 | Permanently unreachable feed detection | Set a feed's `last_fetched_at` to >30 days ago. Planner must create `discovery` remediation plan. | 0 or 1 |
| 3.6 | Stuck plan remediation | Set a plan's `requeue_count >= 2`. Planner must detect and remediate. | 0 or 1 |
| 3.7 | Wave partial failure handling | In a 4-process wave, make 1 fail. Only that step must be marked failed; others continue. | 0 or 1 |
| 3.8 | Plan corruption repair | Corrupt a plan's parent chain. `plans remediate --apply` must fix it. | 0 or 1 |

**Dimension score** = (sum of checkpoints / 8) × 5

---

## Dimension 4: Self-scaling (weight: 10%)

Can the system adapt its resource usage to changing workload?

| # | Checkpoint | How to verify | Score |
|---|-----------|--------------|-------|
| 4.1 | Wave parallelism for fetch/download | Plans with multiple domains must execute in parallel waves of up to 4. | 0 or 1 |
| 4.2 | Throughput emergency priority override | With backlog >200 and non-improving, planner must defer goals 4-9 and focus on 1-3 only. | 0 or 1 |
| 4.3 | Batch limits respected and repeated | Executor must pass `--limit` and repeat commands until backlog is cleared or stalls. | 0 or 1 |
| 4.4 | Dynamic concurrency adjustment | System adjusts wave size or intervals based on load. | 0 or 1 |

**Dimension score** = (sum of checkpoints / 4) × 5

> **Note:** Checkpoint 4.4 requires runtime code changes (not instruction-layer). Expected to score 0 until implemented.

---

## Dimension 5: Self-optimizing (weight: 10%)

Can the system improve its own performance based on historical data?

| # | Checkpoint | How to verify | Score |
|---|-----------|--------------|-------|
| 5.1 | Metrics history persisted | After monitor cycle, `.metrics/<timestamp>.json` must exist with current metrics. | 0 or 1 |
| 5.2 | Historical backlog comparison works | With 2+ metrics files, planner must compare current vs previous backlog and detect non-improving. | 0 or 1 |
| 5.3 | Throughput emergency activates and deactivates | Trigger emergency (backlog >200, non-improving). Verify it activates. Clear backlog. Verify it deactivates. | 0 or 1 |
| 5.4 | Adaptive interval tuning | System adjusts scheduling intervals based on observed throughput. | 0 or 1 |

**Dimension score** = (sum of checkpoints / 4) × 5

> **Note:** Checkpoint 5.4 requires runtime code changes. Expected to score 0 until implemented.

---

## Dimension 6: Error containment (weight: 20%)

Can the system prevent errors from cascading and maintain stability?

| # | Checkpoint | How to verify | Score |
|---|-----------|--------------|-------|
| 6.1 | Unified error taxonomy | All failure reports use codes from `error-taxonomy.md`. No non-canonical codes in quality gate or retry paths. | 0 or 1 |
| 6.2 | Fail-safely rules enforced | Trigger 5 repeated tool errors with same signature. Agent must break the loop. | 0 or 1 |
| 6.3 | Retry limits enforced | Retry a failed action 3 times. Agent must stop and not retry a 4th time. | 0 or 1 |
| 6.4 | Wave failure isolation | One wave member fails. Others complete. Only the failed step is marked failed. | 0 or 1 |
| 6.5 | Fact-check eligibility gated | Attempt to fact-check a `downloaded` article. Must be rejected as ineligible. | 0 or 1 |
| 6.6 | Plan deduplication prevents duplicate work | With an active plan for a scope, planner must NOT create a second plan for the same scope. | 0 or 1 |
| 6.7 | Quality gate blocks bad output | Submit article with 100-char content. Parser must fail it with `parse.out_of_bounds`, not accept it. | 0 or 1 |
| 6.8 | No inter-skill cross-references | Grep skill files for named references to other skills. Must find zero (business-logic routing tables excluded). | 0 or 1 |

**Dimension score** = (sum of checkpoints / 8) × 5

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

## Quick Verification Commands

These commands help verify checkpoints against a running system:

```bash
# Check bootstrap (1.1): empty feed database
news48 stats --json | jq '.feeds.total'

# Check stale plan recovery (1.3): any plans stuck in executing
news48 plans list --json | jq '[.[] | select(.status == "executing")]'

# Check monitoring health (2.1-2.8): run monitor and inspect report
cat .monitor/latest-report.json | jq '.status, .metrics'

# Check metrics history (5.1): files exist
ls -la .metrics/*.json

# Check feedback loop (3.1): executor feedback files
ls -la .plans/feedback/

# Check error taxonomy (6.1): grep for non-canonical codes
grep -rn 'quality_gate\.\|normalization\.' agents/skills/

# Check cross-references (6.8): grep for skill-to-skill references
grep -rn 'loaded in this prompt\|see the.*skill\|see the.*procedure loaded' agents/skills/ --include='*.md'
```

---

## Score History

Record each assessment here for trend tracking.

| Date | Self-start | Self-monitor | Self-heal | Self-scale | Self-optimize | Error contain | **Overall** | Notes |
|------|-----------|-------------|----------|-----------|--------------|--------------|-------------|-------|
| 2026-04-12 (original) | 4.0 | 3.0 | 3.0 | 2.0 | 2.0 | 4.0 | **3.0** | Pre-fix baseline |
| 2026-04-12 (post-fix) | 4.5 | 4.5 | 4.0 | 2.5 | 3.0 | 4.5 | **4.0** | All critical/high fixes applied |
| 2026-04-12 (reassess) | 5.0 | 4.7 | 5.0 | 3.75 | 3.75 | 5.0 | **4.7** | Strict checkpoint scoring; 4.4+5.4 remain FAIL (no runtime code); 2.3 PARTIAL |
| | | | | | | | | |
