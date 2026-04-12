# Skill: Avoid duplicate plans

## Scope
Always active — planner must avoid duplicate work.

## Rules
1. Before creating a plan, run `list_plans` for pending and executing status.
2. One plan per concern.
3. If a same-family active plan exists in the same execution scope, reuse it.
4. Use `parent_id` for sequencing dependencies.
5. Fetch/download/parse execution work may have multiple active plans when their scopes differ.
6. For download backlog, allow one campaign plan plus one active child plan per feed/domain scope.
7. Do not dedupe a feed-scoped child plan against the campaign plan that groups it.
