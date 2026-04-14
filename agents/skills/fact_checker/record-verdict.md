# Record Verdict

Record the fact-check verdict in the database.

## Steps

1. After evaluating all claims, determine the overall verdict:
   - `positive` — most claims are supported
   - `negative` — most claims are refuted
   - `mixed` — evidence is inconclusive
2. Use `news48 articles update <id> --fact-check-status <status>` to record the verdict.
3. Log the fact-check result using the `save_lesson` tool for future reference.

## Verdict Criteria

- **Positive**: At least 70% of claims are supported by evidence
- **Negative**: At least 70% of claims are refuted by evidence
- **Mixed**: Evidence is inconclusive or split
