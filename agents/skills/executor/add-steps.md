# Skill: Add execution steps when required

## Scope
Active when plan requires discovery of additional work.

## Rules
1. If during execution you discover work the plan did not anticipate, use `update_plan` with `add_steps`.
2. After adding steps, execute the new steps.
3. New step IDs must follow the existing naming pattern.
