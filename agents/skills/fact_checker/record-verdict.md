# Record Verdict

Record the fact-check verdict in the database.

## Steps

1. After evaluating all claims, determine the overall verdict:
   - `verified` — the material claims checked are supported by strong evidence
   - `disputed` — one or more material claims are contradicted by strong evidence
   - `unverifiable` — the material claims could not be proved or disproved with sufficient confidence
   - `mixed` — the article contains a meaningful mix of supported and disputed claims
2. Use `uv run news48 articles check <id> --status <status> --result "<summary>" --json` to record the verdict.
3. Log the fact-check result using the `save_lesson` tool for future reference only when it reveals a reusable workflow insight.

## Verdict Criteria

- **Verified**: The central checked claims are supported by strong evidence and no major checked claim is materially false.
- **Disputed**: One or more central checked claims are materially false or misleading.
- **Unverifiable**: Available evidence is insufficient, conflicting, or too weak to support a stronger verdict.
- **Mixed**: The article contains both supported and disputed central claims.
