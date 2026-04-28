# Extract Claims

Extract the material factual claims from the article that need verification.

## Steps

1. Read the article metadata and parsed content:
   ```
   news48 articles info <id> --json
   news48 articles content <id> --json
   ```
2. Identify **3–5 key factual claims** (hard limit: 5).
3. **Each claim MUST have a non-empty `text` field.** Never write claims
   with empty, placeholder, or truncated text. The `text` field must be a
   complete, standalone factual statement.
4. Focus on verifiable statements: specific numbers, events, named entities,
   direct quotes, dates, and attributions. Skip opinion, prediction, and
   rhetorical framing.
5. Prioritize claims that are central to the article's thesis — if you can
   only verify a handful, verifying the central ones matters most.

## Claim selection policy

- **HARD LIMIT: Maximum 5 claims per article.** Never extract more than 5. If you identify more than 5 candidates, pick the 5 most material to the article's thesis.
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

Return an internal list of claim strings. Then **immediately save them to
the database** before searching for evidence:

1. Write the claims to a JSON file with placeholder verdicts:
   ```bash
   cat > /tmp/fc-claims-<id>.json << 'CLAIMS_EOF'
   [
     {"text":"<claim 1>","verdict":"unverifiable","evidence":"Pending","sources":[]},
     {"text":"<claim 2>","verdict":"unverifiable","evidence":"Pending","sources":[]}
   ]
   CLAIMS_EOF
   ```
2. Submit to DB: `news48 articles check <id> --claims-json-file /tmp/fc-claims-<id>.json --pending --json`
3. Query back: `news48 articles claims <id> --json`

The DB enforces a hard limit of 5 claims. Only claims that made it into
the DB should proceed to **fc-follow-plan** (create a plan with one step
per DB claim). This guarantees you never search for more than 5 claims,
regardless of how many you extracted.
