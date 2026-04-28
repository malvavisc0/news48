# Follow Fact-Check Plan

Execute a fact-check plan step by step, verifying each claim against
external evidence.

## When to Plan

After saving claims to the DB and querying them back, create a plan
with one step per claim. This gives structure, progress tracking, and
crash resilience.

## Create the plan

```python
create_plan(
    reason="Fact-check article <id>",
    task="Fact-check article <id>: verify each claim against external sources",
    steps=[
        "Verify claim 1: <claim text>",
        "Verify claim 2: <claim text>",
        ...
    ],
    success_conditions=[
        "All claims have verdicts (verified/disputed/unverifiable/mixed)",
        "All verified claims have ≥2 independent sources",
        "Claims re-submitted to DB with real verdicts",
    ],
    scope_type="fact_check",
    scope_value="<article_id>",
)
```

## Execute each step

For each step (claim):

1. `update_plan` → mark step as `executing`
2. `perform_web_search` with neutral queries about the claim
3. `fetch_webpage_content` on the most promising results
4. Evaluate evidence and assign a verdict
5. `update_plan` → mark step as `completed`, result = verdict + evidence summary

## After all steps complete

1. **Query the DB for claim text**: `news48 articles claims <id> --json`
   — You MUST use the `claim_text` from the DB query as the `text` field
   in the final JSON. Never leave `text` empty or omit it.
2. Build the final claims JSON array. Each entry MUST have:
   - `text` — copied from the DB `claim_text` (step 1 above)
   - `verdict` — from your evidence evaluation
   - `evidence` — your evidence summary
   - `sources` — URLs that provided evidence
3. Re-submit with `--force`: `news48 articles check <id> --claims-json-file ... --result "..." --force --json`
4. Verify with `news48 articles claims <id> --json`
5. Mark the plan as completed: `update_plan(plan_status="completed")`

This ensures the plan is in terminal state and won't be flagged as
orphaned by the sentinel.

## Rules

- **The number of plan steps MUST equal the number of claims returned by
  `articles claims <id> --json`.** If you extracted more than 5 claims,
  discard the extras before creating the plan. Never create a plan with
  more steps than the DB query returned.
- Never start a new step before completing the current one.
- If evidence is insufficient after retries, mark the step as `completed`
  with verdict `unverifiable` — do not leave steps in `executing` state.
- Do not add extra steps or check claims outside the plan.
