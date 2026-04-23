# Skill: Verify parser result

## Scope
Always active — parser must emit a final status line that the caller can verify.

## Rules
1. After the update attempt, emit a concise success or failure line.
2. Do not run extra verification commands only to inspect `parsed_at`.
3. The caller verifies whether the article update persisted successfully.

## Final Response
After tool execution, emit one concise status line:
- Success: `PARSE_OK article_id=<id> fields=title,summary,content,categories,tags,countries,sentiment`
- Failure: `PARSE_FAIL article_id=<id> reason=<code>`
