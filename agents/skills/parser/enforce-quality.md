# Skill: Enforce parser quality

## Scope
Always active — parser must block low-quality or invented output.

## Quality Gate (Before Final Update)
Ensure all are true before writing content:
- Title non-empty, factual, 8-140 chars
- Title must be descriptive and specific — it must tell the reader what happened. Reject vague, deictic, or clickbait titles that use pronouns or references without a subject (e.g., "this is what happened today", "here's why it matters", "you won't believe what they did"). Rewrite them to include the actual subject and event.
- Summary 1-3 sentences, 40-420 chars, not equal to title
- **No HTML tags** in title, summary, or content. All output must be plain text. If the source contains HTML entities or tags, strip them completely before storing.
- Content at least 600 chars (sources genuinely brief may have 200+ chars — below 200 chars is unacceptable regardless of source)
- Sentiment: `positive|negative|neutral`
- Countries: ISO-2 lowercase only
- Categories: from controlled set, 1-3
- Tags: 2-8 when source provides signals

## Fidelity Checks
- No invented entities, dates, numbers, causal claims
- Preserve uncertainty words where source uncertain
- Preserve attribution for disputed statements

## Failure Handling
If any quality gate or fidelity check fails:
```bash
news48 articles fail ARTICLEID --error "Failed parser quality gate: <reason>" --json
```

Failure reason codes (must use codes from the canonical error taxonomy in `shared/error-taxonomy.md`):
- `parse.duplicate_title` — summary duplicates the title
- `parse.out_of_bounds` — title, summary, or content length outside limits
- `parse.invalid_field` — country code, category, or sentiment normalization failed
- `parse.fidelity` — invented facts or missing core facts
- `parse.html_in_output` — HTML tags found in title, summary, or content
- `parse.clickbait_title` — title is vague, deictic, or clickbait without a descriptive subject
