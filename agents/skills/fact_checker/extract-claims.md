# Extract Claims

Extract the key factual claims from the article that need verification.

## Steps

1. Read the article metadata and parsed content using `uv run news48 articles info <id> --json` and `uv run news48 articles content <id> --json`.
2. Identify the main factual claims in the article (typically 3-7 claims).
3. Focus on verifiable statements, not opinions or analysis.
4. Prioritize claims that are central to the article's thesis.

## Claim Selection Policy

- Prefer claims that can be checked against external reporting, official statements, or primary documents.
- Skip pure opinion, prediction, or rhetorical framing unless it contains a concrete factual assertion.
- If the article contains many claims, prioritize the most material ones rather than exhaustively checking trivia.

## Output

Return a list of claims to verify, each as a separate statement.
