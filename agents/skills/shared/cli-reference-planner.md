# Skill: Planner agent CLI reference

## Scope
Always active — planner must only use documented commands.

Evidence commands are loaded separately in the shared evidence commands reference. This file lists planner-specific action commands only.

## Plan Management Commands
- `news48 plans remediate --json` — preview blocked or corrupted plans that need repair.
- `news48 plans remediate --apply --json` — repair blocked or corrupted plans (actually applies the fixes).

## Bootstrap Command
- `news48 seed FILE --json` — insert feed URLs from a text file. Use only when `feeds.total` is 0.

## Forbidden Commands
Planner must NOT run:
- `news48 fetch`, `news48 download`, `news48 parse` (executor work)
- `news48 feeds add`, `news48 feeds update`, `news48 feeds delete`
- `news48 articles update`, `news48 articles delete`, `news48 articles feature`, `news48 articles breaking`
- `news48 cleanup purge`
- `news48 agents start`, `news48 agents stop`, `news48 agents dashboard`
- `news48 feeds rss`, `news48 sitemap generate`

## Selection Heuristic
1. Run `news48 stats --json` first for a full system overview.
2. Use `news48 plans list --json` to check for existing active plans before creating new ones.
3. Use `news48 feeds list --json` and `news48 articles list --json` to identify backlog.
4. If `feeds.total` is 0, bootstrap with `news48 seed` instead of creating observation-only plans.