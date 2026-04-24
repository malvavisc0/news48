# Record Verdict

Record the fact-check results in the database. The article's overall verdict
is **derived** from the per-claim verdicts — you only submit the individual
claims.

## Steps

1. After evaluating every claim, build a JSON array. Each entry must have
   these keys (see **cli-reference-fact-checker** for the authoritative schema):
   - `text` — the factual claim extracted from the article (keep it faithful).
   - `verdict` — one of `verified`, `disputed`, `unverifiable`, `mixed`.
   - `evidence` — a short explanation of what you found (1–2 sentences).
   - `sources` — the array of URLs that actually provided evidence.
2. Write the claims JSON array to a temp file:
   ```bash
   cat > /tmp/fc-claims-<article_id>.json << 'CLAIMS_EOF'
   <json_array>
   CLAIMS_EOF
   ```
3. Write the `--result` summary — one or two sentences explaining the
   overall rollup verdict.
4. Run:
   ```
   news48 articles check <id> \
       --claims-json-file /tmp/fc-claims-<article_id>.json \
       --result "<summary>" \
       --json
   ```
   Do **not** pass `--status` — the rollup is derived automatically.
5. Immediately verify with:
   ```
   news48 articles claims <id> --json
   ```
   Confirm the expected number of claims landed and that each has the
   intended verdict, evidence text, and sources list.
6. Only when a run reveals a reusable workflow insight, log it via the
   `save_lesson` tool.

## Per-claim verdict criteria

- **verified** — At least two independent, reputable sources corroborate the
  claim. `sources` must contain those URLs.
- **disputed** — Reliable sources contradict the claim, or report a
  materially different version of it.
- **unverifiable** — Evidence is insufficient, conflicting, or too weak to
  support a stronger verdict. An empty `sources` array is only acceptable
  here.
- **mixed** — Parts of the claim are supported and parts are not; or
  reputable sources disagree on scope/degree.

## Overall verdict rollup

The article-level verdict is computed by the CLI:

| If per-claim verdicts are… | Article verdict |
|---|---|
| all `verified` | `verified` |
| any `disputed` | `disputed` |
| mix of `verified` + `mixed`/`unverifiable` | `mixed` |
| all `unverifiable` | `unverifiable` |

## Example

```bash
# Step 1: Write claims to file
cat > /tmp/fc-claims-4211.json << 'CLAIMS_EOF'
[
  {"text":"Officials narrowed the draft export package.",
   "verdict":"verified",
   "evidence":"Reuters, FT, and Bloomberg independently report the narrower scope.",
   "sources":["https://reuters.com/…","https://ft.com/…","https://bloomberg.com/…"]},
  {"text":"Next 48 hours are critical for a final announcement.",
   "verdict":"disputed",
   "evidence":"Politico and WSJ quote named officials describing a weeks-long timeline.",
   "sources":["https://politico.eu/…","https://wsj.com/…"]}
]
CLAIMS_EOF

# Step 2: Submit
news48 articles check 4211 \
    --claims-json-file /tmp/fc-claims-4211.json \
    --result "Core policy claims verified; the announcement-timeline claim is disputed." \
    --json