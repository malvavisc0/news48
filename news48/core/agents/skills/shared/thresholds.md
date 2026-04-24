# Skill: Health thresholds reference

## Scope
Always active for sentinel agent — single source of truth for all health thresholds.

## Thresholds

| Metric | Warning | Critical |
|--------|---------|----------|
| Total feeds | — | 0 (empty DB, needs seeding) |
| Database size | 100 MB | 500 MB |
| Feed stale (no recent fetch) | 10 minutes | 30 minutes |
| Articles today | 0 | 0 for >1 hour |
| Download failure rate | 10% | 25% |
| Parse failure rate | 10% | 25% |
| Malformed parsed articles | ≥ 1 | ≥ 10 |
| Articles with missing fields | ≥ 5 | ≥ 20 |
| Articles older than 48h | present | 100+ |

## Self-Healing Metrics (Do NOT Create Plans)

The following backlogs are handled by the orchestrator's automated background loops or scheduled agents and **must not** trigger plan creation:

- **Empty article backlog** (download backlog) — the `_download_loop` runs every 30s and processes up to 100 articles per cycle.
- **Downloaded article backlog** (parse backlog) — the parser is triggered automatically after each download batch, and also runs on its own schedule.
- **Fact-check backlog** — the `fact_checker` agent runs on its own 5-minute schedule with up to 3 concurrent instances. Creating executor plans for fact-check backlog causes an infinite timeout→requeue loop because a single executor cannot complete the work within its 30-minute runtime limit.

These metrics may still be reported in the sentinel report for visibility, but they should **never** result in fix plans.

## Feed Fetching (MUST Create Plans)

Feed fetching is the pipeline inflow — without it, no articles enter the system and all downstream backlogs stay at zero. The sentinel **must** create a fetch plan when:

- **Feed stale threshold breached** — no successful fetch in the last 10 minutes (WARNING) or 30 minutes (CRITICAL).
- **Articles today is 0** — no new articles have been inserted today, meaning feeds have not been fetched recently enough.

The fetch plan should contain a single step: `news48 fetch --json`. Check `news48 plans list --json` first to avoid duplicating an existing pending fetch plan.

## Rate Denominator Semantics
All failure rates in this table are computed as **lifetime rates** (since system initialization), not per-cycle or per-24h rates. The denominator includes all articles processed since the system started.

If a denominator is zero, the rate is **undefined** (not 0%). Undefined rates must not trigger threshold breaches — record them as `null` with an "insufficient sample" note.

## Classification
Compute strictly in this order:
1. `CRITICAL` if any critical threshold is breached
2. `WARNING` if no critical but one or more warning thresholds are breached
3. `HEALTHY` otherwise

## Rules
- Use only metrics exposed by documented CLI output.
- If a denominator is zero or a metric cannot be proved from current evidence, call that out explicitly instead of inferring.
- Do not duplicate these thresholds in other skills or instructions — this is the canonical source.