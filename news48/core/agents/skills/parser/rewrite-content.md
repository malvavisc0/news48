# Skill: Rewrite content with originality and depth

## Scope
Always active — parser must produce fully original, substantive content.

## Non-Negotiable Standards

### 1. Content Originality
Every piece of output content must be fully rewritten in original language. There must be zero verbatim copying or superficial word-swapping from the source material.

**Hard rules:**
- No phrase of 4 or more consecutive words may match the source article
- Every sentence must be structurally and lexically different from any sentence in the source
- Do not merely swap synonyms while keeping the same sentence skeleton
- Restructure arguments, vary sentence patterns, change clause order, and combine or split ideas
- Demonstrate genuine comprehension by presenting information through a fresh editorial lens

### 2. Content Depth
Output must be substantive and comprehensive — never a hollow summary that strips away everything useful.

**Hard rules:**
- 3–15 paragraphs, each at least 150 characters
- Total content: 1,200–10,000 characters
- Every paragraph must carry substantive information — no filler, no throat-clearing, no meta-commentary about the article itself
- Preserve quantitative facts, named entities, dates, and causal relationships from the source
- If the source discusses trade-offs, disagreements, competing perspectives, or uncertainty, reflect that nuance
- Include the "why" and "how" — not just the "what"

### 3. Editorial Tone
- Write as a knowledgeable editor summarizing for an informed reader
- Remove noise, repetitions, filler, and boilerplate phrases like "The article discusses" or "Key facts include"
- Use clear, plain English — avoid jargon unless the subject demands it
- Maintain factual accuracy and preserve attribution for disputed or unverified claims

### 4. Plain Text Only — No Markdown
All output must be plain text prose. Do not use any markdown formatting syntax.

**Forbidden patterns:**
- `**bold text**` or `__bold text__` — just write the words
- `*italic text*` or `_italic text_` — just write the words
- `# Heading` or `## Subheading` — use paragraph structure instead
- `---` horizontal rules — use paragraph breaks instead
- `> blockquote` — integrate quoted material into prose
- `- bullet list` or `1. numbered list` — write as flowing sentences
- `` `code` `` backticks — just write the term normally
- `[text](url)` link syntax — reference sources by name in prose
- `~~strikethrough~~` — just omit the struck text

**Rule:** If you need emphasis, use word choice and sentence structure — not markup. Write every paragraph as continuous prose separated by blank lines.

### 5. Strip Navigation and UI Artifacts
Source articles — especially from RSS feeds or website excerpts — often include navigation prompts, "read more" links, or subscription calls-to-action. These must be completely removed from the output.

**Common patterns to strip:**
- "Continue reading" / "Continue reading on the website"
- "Read more" / "Read the full article" / "Read the full story"
- "Click here to read" / "Click here for the full article"
- "Subscribe to read" / "Sign in to continue"
- "Keep reading" / "Read on" / "More on this story"
- "Related stories" / "See also" / "You may also like"
- Any similar prompt that directs the reader to another page or action

**Rule:** If a sentence or phrase exists solely to direct the reader to read more content elsewhere, remove it entirely. Do not paraphrase it. Do not include it in the summary or content.

## Examples

### Acceptable Rewrite

**Source sentence:**
> "The Federal Reserve raised interest rates by 0.25 percentage points on Wednesday, bringing the benchmark federal funds rate to a range of 5.25% to 5.5%, the highest level in 22 years."

**Acceptable output:**
> "In its latest move to combat persistent inflation, the Fed pushed its key lending rate up by a quarter point to between 5.25% and 5.5% — a level not seen since 2001."

*Why acceptable:* Different sentence structure, different vocabulary, adds context ("to combat persistent inflation"), uses dash for editorial flow, rephrases "22 years" as "since 2001."

### Unacceptable: Verbatim Copy

**Source sentence:**
> "The Federal Reserve raised interest rates by 0.25 percentage points on Wednesday, bringing the benchmark federal funds rate to a range of 5.25% to 5.5%, the highest level in 22 years."

**Unacceptable output:**
> "The Federal Reserve raised interest rates by 0.25 percentage points on Wednesday, bringing the benchmark federal funds rate to a range of 5.25% to 5.5%."

*Why unacceptable:* Copied verbatim from source with only a trailing clause removed. Multiple phrases of 4+ consecutive words match exactly.

### Unacceptable: Superficial Word-Swap

**Unacceptable output:**
> "The Federal Reserve increased interest rates by 0.25 percentage points on Wednesday, taking the benchmark federal funds rate to a range of 5.25% to 5.5%."

*Why unacceptable:* Only two words changed ("raised"→"increased", "bringing"→"taking"). The sentence skeleton is identical. This is not genuine rewriting.

### Unacceptable: Shallow Summary

**Source:** A 1500-word article about a trade agreement covering tariffs, agricultural exports, digital trade provisions, dispute resolution mechanisms, and geopolitical implications.

**Unacceptable output:**
> "Two countries signed a new trade agreement. The deal covers various economic sectors."

*Why unacceptable:* Strips away all substance. No specific details, no context, no depth. Fails the 1200-char minimum and the requirement for substantive paragraphs.

## Content via File
Always write content to temp file, then use `--content-file`:
```bash
cat > /tmp/parsed_ARTICLEID.txt << 'CONTENT_EOF'
Content here...
CONTENT_EOF
```

## Self-Validation Checklist
Before finalizing content, mentally verify every item:
- [ ] No sentence is structurally identical to any source sentence
- [ ] No phrase of 4+ consecutive words is copied from source
- [ ] Content is 1,200–10,000 characters across 3–15 paragraphs
- [ ] Each paragraph is at least 150 characters and carries substantive information
- [ ] All key facts, figures, named entities, and dates from extraction are present
- [ ] Nuance, context, and supporting details are preserved — not stripped away
- [ ] The tone is editorial — not a mechanical summary or bullet-point dump
- [ ] No boilerplate phrases ("The article discusses", "Key facts include", etc.)
