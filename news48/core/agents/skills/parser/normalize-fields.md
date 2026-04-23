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
- Examples:
  - ✅ "Fed lifts rates to 22-year high in inflation fight"
  - ❌ "Fed Lifts Rates To 22-Year High In Inflation Fight"
  - ❌ "FED LIFTS RATES TO 22-YEAR HIGH IN INFLATION FIGHT"

### Size Bounds
- Title: 8-140 characters
- Summary: 40-420 characters, 1-3 sentences, not duplicate of title
