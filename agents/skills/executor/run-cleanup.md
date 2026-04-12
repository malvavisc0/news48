# Skill: Execute cleanup plans

## Trigger
Active when plan family is retention or cleanup.

## Rules
1. **Check state**: `news48 cleanup status --json`
2. **Run cleanup**: `news48 cleanup run --json`
3. **Purge only if plan explicitly says**: `news48 cleanup purge --force --json`
4. **Verify**: `news48 cleanup status --json` shows zero articles older than 48h.

## Constraints
- Never run `news48 cleanup purge` without checking `news48 cleanup status` first.
