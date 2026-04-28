# Search Evidence

For each extracted claim, search for evidence that supports or refutes it,
then assign a per-claim verdict.

## Tools

- `perform_web_search(query: str)` — Search the web for evidence.
- `fetch_webpage_content(url: str)` — Read the full text of a page.

## Steps

1. For each claim, craft one or more neutral search queries that do not
   assume the claim is true. Prefer the names, numbers, and dates from the
   claim itself.
2. Call `perform_web_search` to find candidate sources.
3. Call `fetch_webpage_content` on the most promising results — primary
   sources, official statements, regulatory filings, or reputable outlets.
4. Compare what each source actually says against the original claim.
5. Assign a per-claim verdict using the same vocabulary the CLI accepts:
   - `verified` — ≥ 2 independent reputable sources corroborate the claim.
   - `disputed` — reliable sources contradict the claim or report a
     materially different version of it.
   - `unverifiable` — evidence is insufficient, conflicting, or weak; no
     source either confirms or refutes the claim cleanly.
   - `mixed` — parts of the claim are supported and parts are not, or
     reputable sources disagree on scope / degree.

## Source tracking

For each claim, record the URLs of the pages that actually supplied
evidence. These go into the `sources` array submitted to `articles check`
(see **record-verdict**) and are rendered next to
the claim on the website. Do **not** include URLs you merely searched but
did not use as evidence.

## Source exclusion — article's own URL

**Never use the article's own URL as a source.** The article being
fact-checked cannot serve as evidence for its own claims — that would be
circular verification. If the article's URL appears in search results,
skip it entirely: do not fetch it, and do not add it to the `sources`
array. Only independent, external references are valid sources.

## Budget and limits

- Up to 2 additional search/fetch retries per claim path before falling back
  to `unverifiable`.
- Never assign `verified` without at least two independent sources.
- Never fabricate a URL. If a source does not exist or could not be
  fetched, leave it out.
