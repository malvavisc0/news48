# Skill: Handle orchestrator restart

## Scope
Always active for all agents — agents must be resilient to orchestrator restarts.

## Background
The orchestrator may restart while an agent is running. When this happens:
- The agent subprocess **continues running** — it is not killed by the orchestrator restart.
- The orchestrator reloads state on startup and discovers the agent's PID in a previous running state.
- If the agent process is still alive, the orchestrator re-attaches and waits for it to finish.
- If the agent process has exited, the orchestrator treats it as completed (checks exit code from logs).

## Rules for Agents
1. **Always write terminal state before exiting.** Whether a plan is marked `completed` or `failed`, an article is updated, or a report is written — persist the outcome before the agent process ends. This ensures the orchestrator can detect the result regardless of restart timing.
2. **Do not depend on orchestrator task context mid-run.** The `task_context` dict is passed once at agent start. If the orchestrator restarts, no new context will be injected. Agents must use their own CLI evidence to verify state rather than relying on stale context values.
3. **Idempotent operations only.** If an agent run is interrupted and restarted, the same work should be safe to re-execute. All pipeline commands (`fetch`, `download`, `parse`, `cleanup`) are idempotent by design.
4. **Plan claims survive restarts.** A claimed plan remains claimed by its executor PID. The orchestrator's `_recover_stale_plans` will only reset plans claimed by dead processes whose timeout has expired. As long as the executor process is alive, its claim is safe.
5. **Article claims survive restarts.** A claimed article remains claimed by its owner. The orchestrator's `_recover_stale_articles` only releases claims older than the timeout threshold from dead processes.

## What the Orchestrator Does on Restart
1. Loads persisted orchestrator state
2. Runs `_recover_stale_plans()` — resets plans stuck in `executing` by dead processes
3. Runs `_recover_stale_articles()` — releases article claims from dead processes
4. Archives old completed/failed plans
5. Resumes the scheduling loop

## Agent Implications
- If an agent was mid-execution when the orchestrator restarted, it will complete normally and exit.
- The orchestrator will collect its result on the next tick when it discovers the process has exited.
- No agent action is needed — the design is self-healing as long as agents follow rule 1 (write terminal state before exit).
