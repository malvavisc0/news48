# Skill: Extract source-supported facts

## Scope
Always active — parser must extract only explicit source evidence, with full depth.

## Rules
1. Identify what is explicitly present in source.
2. Never invent dates, entities, countries, or sentiment.
3. Preserve named entities, quantitative facts, dates, and causality direction.
4. Preserve uncertainty language where present in source.
5. Preserve attribution for disputed or unverified statements.

## Depth and Completeness Requirements

The extraction must be comprehensive enough to support a substantive rewrite. A shallow extraction produces a shallow output.

6. **Extract ALL significant facts** — not just the headline claim. Capture supporting evidence, statistics, quotes, and contextual details.
7. **Capture the "why" and "how"** — not just the "what." If the source explains causes, motivations, mechanisms, or consequences, extract those.
8. **Preserve nuance** — if the source discusses trade-offs, competing perspectives, disagreements, limitations, or uncertainty, capture that nuance. Do not flatten complex information into oversimplified statements.
9. **Note quantitative details** — specific numbers, percentages, dates, timeframes, and measurements. These add credibility and depth to the rewrite.
10. **Capture key quotes** — direct quotes from named sources add authority and voice. Preserve them for use in the rewrite (paraphrased, not copied verbatim).

## What to Extract

For a standard news article, aim to capture:
- **Core event/claim**: What happened or what is being asserted
- **Key actors**: Who is involved (people, organizations, governments)
- **Supporting evidence**: Data, statistics, studies, documents cited
- **Context**: Background information, prior events, broader significance
- **Implications**: Consequences, next steps, expert assessments
- **Uncertainty/caveats**: What is unknown, disputed, or conditional

## Anti-Pattern: Headline-Only Extraction

**Unacceptable:** Extracting only the main claim and ignoring all supporting detail.

Source: A 1200-word article about a new regulation that includes the specific requirements, affected industries, compliance timelines, industry reactions, and legal challenges.

**Unacceptable extraction:**
> "New regulation announced. Affects multiple industries."

**Acceptable extraction:**
> "New regulation requires X by [date]. Applies to [industries]. Compliance deadline: [date]. Industry groups oppose due to [reasons]. Legal challenge expected from [entity]. Estimated cost: $[amount]. Previous attempt in [year] failed because [reason]."
