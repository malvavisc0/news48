# Extract Claims

Extract the material factual claims from the article that need verification.

## Steps

1. Read the article metadata and parsed content:
   ```
   news48 articles info <id> --json
   news48 articles content <id> --json
   ```
2. Identify **2–5 key factual claims** (absolute maximum: 5).
3. Focus on verifiable statements: specific numbers, events, named entities,
   direct quotes, dates, and attributions. Skip opinion, prediction, and
   rhetorical framing.
4. Prioritize claims that are central to the article's thesis — if you can
   only verify a handful, verifying the central ones matters most.

## Claim selection policy

- **HARD LIMIT: Maximum 5 claims per article.** Never extract more than 5.
- Prefer claims that can be checked against external reporting, official
  statements, regulatory filings, or primary documents.
- Skip pure opinion, forecast, analysis, or rhetorical framing unless it
  contains a concrete factual assertion that could be falsified.
- If the article contains many claims, prioritize the most material ones
  rather than exhaustively checking trivia.
- Preserve the claim's meaning when you rewrite it: it should still be a
  faithful, standalone statement that a reader could verify without
  re-reading the article.

## Output

Return an internal list of claim strings. This list is the input for
**search-evidence** and then **record-verdict**. The exact `text` you list here is
what will be persisted in the `claims.claim_text` column, so write each
entry as a clean, self-contained sentence.
