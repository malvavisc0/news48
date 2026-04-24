# Skill: Normalize parsed fields

## Scope
Always active — parser must enforce canonical taxonomy.

## Rules
### Sentiment
- Must be: `positive`, `negative`, or `neutral`
- Never leave blank
- Use `neutral` for mixed or factual-only tone

### Countries
- ISO-2 lowercase codes only, comma-separated (e.g., `us,ir,il`)
- No full names like `canada` or `united states`
- No spaces between codes — use commas as the only separator
- Validate: every token (split by comma) must match `^[a-z]{2}$`

### Categories
- Controlled set: `world`, `politics`, `business`, `technology`, `science`, `health`, `sports`, `travel`, `entertainment`, `others`
- 1-3 categories only
- Prefer broad categories

### Tags
- Lowercase, comma-separated, no duplicates
- 2-8 tags when source provides signals

### Title Case
- Use **sentence case** only: capitalize the first word and proper nouns only
- Do NOT use Title Case, ALL CAPS, or camelCase
- **Sentence case does NOT mean lowercasing everything.** Proper nouns must always retain their capitalization.

#### Proper Nouns — Always Capitalize
The following are proper nouns and must always be capitalized in titles, regardless of their position:
- **Country names:** Pakistan, Iran, United States, China, Israel, Ukraine, etc.
- **City/region names:** Gaza, Washington, Beijing, etc.
- **People's names:** Biden, Netanyahu, etc.
- **Organizations:** NATO, United Nations, WHO, EU, etc.
- **Acronyms and abbreviations:** US, UK, UN, AI, GDP, etc. (use their standard capitalization)
- **Languages:** English, Arabic, Mandarin, etc.
- **Named events/institutions:** Federal Reserve, Supreme Court, etc.

#### Examples
  - ✅ "US and Iran blockade standoff intensifies as Pakistan pushes for peace talks"
  - ✅ "Fed lifts rates to 22-year high in inflation fight"
  - ✅ "WHO approves new malaria vaccine for use across sub-Saharan Africa"
  - ❌ "Us and iran blockade standoff intensifies as pakistan pushes for peace talks" (proper nouns lowercased)
  - ❌ "Fed Lifts Rates To 22-Year High In Inflation Fight" (Title Case — only proper nouns should be capitalized)
  - ❌ "FED LIFTS RATES TO 22-YEAR HIGH IN INFLATION FIGHT" (ALL CAPS)

### Size Bounds
- Title: 8-140 characters
- Summary: 40-420 characters, 1-3 sentences, not duplicate of title

### Summary Style
- Summaries must never start with meta-references about the article itself
- Forbidden openings: "This article...", "This story...", "The article...", "In this article...", "According to this article...", "This report...", "The report..."
- Summaries must start directly with the substantive content — what happened, who was involved, what the impact is
- ✅ "Fed raises rates to 22-year high as inflation fight continues"
- ❌ "This article discusses the Federal Reserve's decision to raise interest rates"
