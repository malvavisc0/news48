# Skill: Avoid duplicate plans

## Trigger
Always active — planner must avoid duplicate work.

## Rules
1. Before creating a plan, run `list_plans` for pending and executing status.
2. One plan per concern.
3. If a same-family active plan exists (pending/executing), reuse it.
4. Use `parent_id` for sequencing dependencies.
5. Fetch/download/parse: at most one active plan per family and parent scope.
