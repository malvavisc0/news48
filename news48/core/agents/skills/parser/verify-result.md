# Skill: Verify parser result

## Scope
Always active — parser must verify its own output is clean and persisted before reporting success.

## Rules
1. After the update attempt, read back the article via `news48 articles info ARTICLE_ID --json` to confirm `parsed_at` is set.
2. Confirm the persisted title, summary, and content match what was staged — no truncation or corruption.
3. If the article info shows `parsed_at` is null or the fields are empty/malformed, record failure rather than reporting success.
4. Only emit `PARSE_OK` after the persisted record has been verified.

## Final Response
After tool execution, emit one concise status line:
- Success: `PARSE_OK article_id=<id> fields=title,summary,content,categories,tags,countries,sentiment`
- Failure: `PARSE_FAIL article_id=<id> reason=<code>`

## Anti-Pattern: Blind Success
Never emit `PARSE_OK` based solely on the shell command exit code. Always verify the persisted record via `articles info` before confirming success.
