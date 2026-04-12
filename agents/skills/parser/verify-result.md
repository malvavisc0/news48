# Skill: Verify parser result

## Trigger
Always active — parser must confirm parsed_at is set.

## Rules
1. After update, run `news48 articles info ARTICLEID --json`
2. Confirm `parsed_at` is set
3. Confirm article was updated successfully

## Final Response
After tool execution, emit one concise status line:
- Success: `PARSE_OK article_id=<id> fields=title,summary,content,categories,tags,countries,sentiment`
- Failure: `PARSE_FAIL article_id=<id> reason=<code>`
