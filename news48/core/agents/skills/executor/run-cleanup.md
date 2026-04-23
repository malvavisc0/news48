# Skill: Execute cleanup plans

## Scope
Active when plan family is retention or cleanup.

## Rules
1. **Check state**: `news48 cleanup status --json`
2. **Run purge**: `news48 cleanup purge --force --json`
3. **Verify**: `news48 cleanup status --json` shows zero articles older than 48h.

## Constraints
- Never run `news48 cleanup purge` without checking `news48 cleanup status` first.
- Always pass `--force` so the command does not prompt for interactive confirmation.
