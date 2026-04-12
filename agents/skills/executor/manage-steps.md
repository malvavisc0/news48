# Skill: Update step progress accurately

## Trigger
Always active — executor must safely manage step transitions.

## Rules
1. Capture canonical step IDs from the claimed plan before first `update_plan`.
2. `step_id` must exactly match an existing plan step ID.
3. Never move a `failed` step back to `completed`.
4. After a step is terminal (`completed`/`failed`), only idempotent same-status updates allowed.
5. Use valid plan statuses only: `pending`, `executing`, `completed`, `failed`.
6. Never fabricate step IDs.
