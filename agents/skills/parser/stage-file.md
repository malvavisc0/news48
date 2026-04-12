# Skill: Stage parsed content to file

## Trigger
Always active — parser must use safe file handoff via /tmp.

## Rules
1. Always write content to `/tmp/parsed_ARTICLEID.txt`
2. Use `--content-file` to reference the temp file.
3. Never pass content as CLI argument.
4. Use only required file writes under `/tmp`.
