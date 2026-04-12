# Skill: Normalize parsed fields

## Scope
Always active — parser must enforce canonical taxonomy.

## Rules
### Sentiment
- Must be: `positive`, `negative`, or `neutral`
- Never leave blank
- Use `neutral` for mixed or factual-only tone

### Countries
- ISO-2 lowercase codes only (e.g., `us,ir,il`)
- No full names like `canada` or `united states`
- Validate: every token must match `^[a-z]{2}$`

### Categories
- Controlled set: `world`, `politics`, `business`, `technology`, `science`, `health`, `sports`, `travel`, `entertainment`, `others`
- 1-3 categories only
- Prefer broad categories

### Tags
- Lowercase, comma-separated, no duplicates
- 2-8 tags when source provides signals

### Size Bounds
- Title: 8-140 characters
- Summary: 40-420 characters, 1-3 sentences, not duplicate of title
