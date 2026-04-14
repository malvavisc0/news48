# Sentinel Business Logic

## Workflow

```mermaid
flowchart TD
    A[Start sentinel cycle] --> B[Gather system metrics]
    B --> C[Evaluate thresholds]
    C --> D{Thresholds breached?}
    D -->|Yes| E[Create fix plans]
    D -->|No| F[Check feed health]
    E --> F
    F --> G{Unhealthy feeds?}
    G -->|Yes| H[Delete problematic feeds]
    G -->|No| I[Write report]
    H --> I
    I --> J[End cycle]
```

## Steps

1. **Gather metrics** — Run `news48 stats --json`, `news48 feeds list --json`, `news48 plans list --json`, and `news48 cleanup health --json`.
2. **Check for empty database** — If total feeds is 0, the database needs seeding. Create a plan for the executor with one step: `news48 seed seed.txt --json`. The file `seed.txt` contains feed URLs and lives in the project root. Skip all other steps (no thresholds to evaluate on an empty system).
3. **Evaluate thresholds** — Compare metrics against the thresholds skill. Classify as HEALTHY, WARNING, or CRITICAL. Note: download and parse backlogs are self-healing (automated by the orchestrator) and must not trigger plan creation.
4. **Detect malformed articles** — Check the `malformed` count from `news48 stats --json`. If > 0, articles exist that were parsed but still contain HTML tags in their title or summary. Create a plan (family: `parse`) for the executor to fix them. Each step should instruct the executor to: read the article via `news48 articles info ARTICLE_ID --json`, rewrite the summary as clean plain text (no HTML), and update the article via `news48 articles update ARTICLE_ID --summary "clean summary" --json`. If the title is also malformed (contains HTML or is vague clickbait), include a `--title "descriptive title"` flag in the same update command. Check `news48 plans list --json` first to avoid duplicating existing pending fix plans for the same issue.
5. **Create fix plans** — If WARNING or CRITICAL for non-automated metrics, use `create_plan` with concrete CLI steps. Check `news48 plans list --json` first to avoid duplicating existing pending plans. **Never create plans for bulk downloads, bulk fetches, or bulk parsing** — these are automated.
6. **Check feed health** — Apply feed-curation rules to detect and delete problematic feeds.
7. **Write report** — Call `write_sentinel_report` with status, metrics, alerts, and recommendations. This writes to `.monitor/latest-report.json`.
8. **Save lessons** — Record any new insight using `save_lesson`.
