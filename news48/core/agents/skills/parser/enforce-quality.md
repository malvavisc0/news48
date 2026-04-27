# Skill: Enforce parser quality

## Scope
Always active — parser must block low-quality, shallow, copied, or invented output.

## Quality Gate (Before Final Update)
Ensure ALL are true before writing content:

### Title Checks
- [ ] Title is non-empty, factual, 8-140 characters
- [ ] **Title uses sentence case** — capitalize only the first word and proper nouns. Do NOT use Title Case, ALL CAPS, or camelCase.
- [ ] **Proper nouns are always capitalized** — country names (Pakistan, Iran, US), city names (Gaza, Washington), people's names, organizations (NATO, WHO), acronyms (UK, EU, UN), and languages must never be lowercased. Sentence case means sentence case, not lowercase-everything.
- [ ] **Title differs from the source article title** — this is non-negotiable. The output title must always be transformed from the original. See title transformation rules below.
- [ ] Title is descriptive and specific — it must tell the reader what happened
- [ ] Title is insight-driven — a reader can look at it and immediately understand what the article covers
- [ ] Title is clean — no clickbait, no vague/deictic phrasing, no ambiguity, no sensationalism
- [ ] Reject titles that use pronouns or references without a subject (e.g., "this is what happened today", "here's why it matters", "you won't believe what they did")
- [ ] Rewrite titles to include the actual subject and event

### Summary Checks
- [ ] Summary is 1-3 sentences, 40-420 characters
- [ ] Summary is not equal to title
- [ ] Summary is not equal to the first sentence of the content
- [ ] Summary does not start with meta-references ("This article...", "This story...", "The article...", "In this article...", "This report...", etc.) — must start directly with substantive content
- [ ] Summary does NOT contain navigation/UI artifacts — phrases like "Continue reading", "Continue reading on the website", "Read more", "Read the full article", "Full story", "Click here to read", "Subscribe to read", "Sign in to continue" must be stripped entirely

### Content Checks
- [ ] **No HTML tags** in title, summary, or content — all output must be plain text. Strip HTML entities and tags completely.
- [ ] **No markdown syntax** in title, summary, or content — all output must be plain text prose. No `**bold**`, `*italic*`, `# headings`, `---` horizontal rules, `>` blockquotes, `- bullet lists`, `` `backticks` ``, or `[text](url)` link syntax. Write prose paragraphs only.
- [ ] **No navigation/UI artifacts** in title, summary, or content — strip phrases like "Continue reading", "Continue reading on the website", "Read more", "Read the full article", "Full story", "Click here to read", "Subscribe to read", "Sign in to continue", "Keep reading", "Read on", "More on this story", "Related stories"
- [ ] **Content is at least 1200 characters** (sources genuinely brief may have 400+ chars — below 400 chars is unacceptable regardless of source)
- [ ] **Content has 3+ substantive paragraphs, each at least 150 characters**
- [ ] **No verbatim or near-verbatim passages from source** — no phrase of 4+ consecutive words may match the source

### Field Checks
- [ ] Sentiment: `positive|negative|neutral`
- [ ] Countries: ISO-2 lowercase only
- [ ] Categories: from controlled set, 1-3
- [ ] Tags: 2-8 when source provides signals

## Title Transformation Rules

The output title MUST always differ from the source article title. This is a hard requirement with no exceptions.

**Acceptable transformations:**
- Rephrasing with different vocabulary and structure
- Adding specificity (e.g., adding a number, date, or key detail)
- Reframing around the key takeaway or implication
- Making implicit information explicit

**Examples:**

| Source Title | ✅ Acceptable Output | ❌ Unacceptable Output |
|---|---|---|
| "Climate Change Report Warns of Rising Sea Levels" | "New Climate Assessment Projects 30cm Sea Level Rise by 2050" | "Climate Change Report Warns of Rising Sea Levels" (unchanged) |
| "Tech Giant Announces Layoffs" | "MegaCorp to Cut 12,000 Jobs in Restructuring Push" | "Tech Giant Announces Layoffs" (unchanged) |
| "Federal Reserve Raises Interest Rates" | "Fed Lifts Rates to 22-Year High in Inflation Fight" | "Federal Reserve Raises Rates" (trivial trim) |
| "Scientists Discover New Species in Amazon" | "Research Team Identifies 14 Previously Unknown Amazon Species" | "New Species Discovered in Amazon" (trivial reorder) |

## Fidelity Checks
- No invented entities, dates, numbers, or causal claims
- Preserve uncertainty words where source is uncertain
- Preserve attribution for disputed statements
- Do not add information not supported by the source

## Failure Handling
If any quality gate or fidelity check fails:
```bash
news48 articles fail ARTICLEID --error "parse.<reason_code>: Failed parser quality gate: <reason>" --json
```

## Failure Reason Codes
Must use codes from the canonical error taxonomy:

| Code | Trigger |
|------|---------|
| `parse.duplicate_title` | Summary duplicates the title |
| `parse.out_of_bounds` | Title, summary, or content length outside limits |
| `parse.invalid_field` | Country code, category, or sentiment normalization failed |
| `parse.fidelity` | Invented facts or missing core facts |
| `parse.html_in_output` | HTML tags found in title, summary, or content |
| `parse.clickbait_title` | Title is vague, deictic, or clickbait without a descriptive subject |
| `parse.verbatim_copy` | Content contains verbatim or near-verbatim passages from source |
| `parse.shallow_content` | Content is too brief or lacks substantive depth (below 1200 chars or fewer than 3 substantive paragraphs) |
| `parse.unchanged_title` | Output title is identical or near-identical to source title |
| `parse.meta_summary` | Summary starts with meta-references instead of substantive content |
| `parse.navigation_artifacts` | Summary or content contains UI/navigation prompts like "Continue reading", "Read more", etc. |
| `parse.markdown_in_output` | Markdown syntax found in title, summary, or content (bold, italic, headings, lists, code, links, etc.) |
