# Skill: Enforce parser quality

## Trigger
Always active — parser must block low-quality or invented output.

## Quality Gate (Before Final Update)
Ensure all are true:
- Title non-empty, factual, 8-140 chars
- Summary 1-3 sentences, 40-420 chars, not equal to title
- Content at least 600 chars (unless source genuinely brief)
- Sentiment: `positive|negative|neutral`
- Countries: ISO-2 lowercase only
- Categories: from controlled set, 1-3
- Tags: 2-8 when source provides signals

## Fidelity Checks
- No invented entities, dates, numbers, causal claims
- Preserve uncertainty words where source uncertain
- Preserve attribution for disputed statements

If any check fails:
```bash
news48 articles fail ARTICLEID --error "Failed parser quality gate: <reason>" --json
```

Reason codes:
- `quality_gate.summary_duplicate_title`
- `quality_gate.summary_out_of_bounds`
- `quality_gate.title_out_of_bounds`
- `normalization.invalid_country_code`
- `normalization.invalid_category`
- `fidelity.invented_fact`
- `fidelity.missing_core_facts`
