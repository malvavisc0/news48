# Skill: Claim one eligible plan

## Trigger
Always active — executor must claim exactly one plan per session.

## Rules
1. Call `claim_plan` **once** at session start.
2. If `result.status == "no_eligible_plans"`: exit immediately. Do not call any more tools.
3. If `result.plan_id` exists: this is your claimed plan. Proceed.
4. Read the plan's `task` and `success_conditions` before executing steps.
5. Never call `claim_plan` again in the same session.
