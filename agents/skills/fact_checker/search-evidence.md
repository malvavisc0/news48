# Search Evidence

Search for evidence supporting or refuting each claim using web search tools.

## Steps

1. For each claim, use `perform_web_search` to find relevant sources.
2. Use `fetch_webpage_content` to read the content of promising search results.
3. Compare the evidence against the original claim.
4. Classify each claim as:
   - `supported` — evidence confirms the claim
   - `refuted` — evidence contradicts the claim
   - `mixed` — evidence is inconclusive or partially supports

## Tools

- `perform_web_search(query: str)` — Search the web for evidence
- `fetch_webpage_content(url: str)` — Read webpage content
