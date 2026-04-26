# Fact-Check Business Logic

## Workflow

```mermaid
flowchart TD
    A[Start fact-check cycle] --> B[Read article info + content]
    B --> C[Extract 2-5 key claims (max 5)]
    C --> D[For each claim: search web evidence]
    D --> E[Assign per-claim verdict]
    E --> F[Build claims JSON array]
    F --> G[articles check --claims-json-file ...]
    G --> H[articles claims <id> --json]
    H --> I{Verification ok?}
    I -->|No| J[Report failure]
    I -->|Yes| K[Return results]
```

## Skills

- **fc-extract-claims** — Extract 2–5 key,
  externally verifiable claims from the article (hard limit: 5 max).
- **fc-search-evidence** — Search the web for
  supporting or refuting evidence and assign a per-claim verdict.
- **fc-record-verdict** — Persist the claims via
  `articles check --claims-json-file` and verify with `articles claims`.
- **cli-reference-fact-checker** —
  Authoritative reference for `articles check` and `articles claims`.

## Persistence model

The article-level `fact_check_status` and `fact_check_result` are stored on
`articles`. The individual claims are stored one-row-per-claim in the
`claims` table (`article_id`, `claim_text`, `verdict`, `evidence_summary`,
`sources`, `created_at`). The overall article verdict is **derived** from
the per-claim verdicts by the CLI — the agent never submits it directly in
the normal flow.

## Invariants

- Exactly one article per run (the one in the task input).
- Submitting a new `--claims-json-file` **replaces** all previous claims for that
  article (idempotent re-check).
- A `verified` per-claim verdict requires ≥ 2 independent reputable sources
  in its `sources` array.
- An empty `sources` array is only valid for an `unverifiable` verdict.
