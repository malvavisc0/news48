# Skill: Fact-checker CLI reference

## Scope
Always active for the fact-checker agent. This is the authoritative list of
action commands the fact-checker is permitted to run. Evidence-only commands
(e.g. `articles info`, `articles content`) live in **cli-reference-evidence**.

## Action commands

### Record per-claim fact-check results
```
news48 articles check <article_id> \
    --claims-json '<JSON_ARRAY>' \
    --result "<short summary>" \
    --json
```

- `--claims-json` (required for the new per-claim workflow) — a JSON array
  of claim objects. Each object MUST have these keys:

  | Key        | Type            | Required | Meaning |
  |------------|-----------------|----------|---------|
  | `text`     | string          | yes      | The exact factual claim, as extracted from the article. |
  | `verdict`  | string enum     | yes      | One of `verified`, `disputed`, `unverifiable`, `mixed`. |
  | `evidence` | string          | yes      | 1–2 sentence summary of what you found. |
  | `sources`  | array of string | yes      | URLs of pages that supplied evidence. Empty array only if `verdict` is `unverifiable`. |

  The CLI also accepts `claim_text` / `evidence_summary` as synonyms of
  `text` / `evidence`, but always write new JSON using the short keys above.

- `--result` — free-text rollup summary explaining why the overall verdict
  was chosen. Referenced directly from the website.
- `--status` — **do not pass this flag in the per-claim workflow.** The
  overall verdict is derived from the per-claim verdicts. Only use
  `--status` as a last-resort fallback when claim evaluation is impossible.
- `--force` — only pass this when a prior fact-check exists and you have
  been explicitly instructed to re-check.
- `--json` — always pass this.

#### Example
```
news48 articles check 4211 \
    --claims-json '[
      {"text":"Officials narrowed the draft export package.",
       "verdict":"verified",
       "evidence":"Reuters, FT, and Bloomberg all report consistent language on the narrower scope.",
       "sources":["https://reuters.com/…","https://ft.com/…","https://bloomberg.com/…"]},
      {"text":"Next 48 hours are critical for a final announcement.",
       "verdict":"disputed",
       "evidence":"Politico and WSJ both quote named officials describing a weeks-long timeline.",
       "sources":["https://politico.eu/…","https://wsj.com/…"]}
    ]' \
    --result "Core policy claims verified; announcement-timeline claim is disputed by two outlets." \
    --json
```

### Inspect recorded claims (self-verification)
```
news48 articles claims <article_id> --json
```
Use this after `articles check` to confirm the claims landed as expected.
Fields returned: `id`, `article_id`, `claim_text`, `verdict`,
`evidence_summary`, `sources` (parsed list), `created_at`, plus a
`verdict_counts` rollup.

## Core rules

1. Only use the action commands listed here. Evidence-only commands come from
   **cli-reference-evidence**.
2. Always pass `--json` to every `news48` command.
3. The claim list you submit **replaces** any previously recorded claims for
   that article (idempotent re-check). Do not try to append.
4. Never record a `verified` verdict for a claim whose `sources` array is
   empty. If no evidence exists, the correct verdict is `unverifiable`.
5. The overall verdict is derived automatically from the per-claim verdicts:
   - all `verified` → `verified`
   - any `disputed` → `disputed`
   - mix of `verified` with `mixed`/`unverifiable` → `mixed`
   - all `unverifiable` → `unverifiable`
6. Do not invent flags, subcommands, or JSON keys. If you need something that
   is not documented here, stop and report it instead of guessing.
