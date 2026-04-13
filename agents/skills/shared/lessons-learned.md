# Skill: Save lessons learned aggressively

## Scope
Always active — every agent MUST save lessons whenever it discovers something new.

## Why This Matters
You have a `save_lesson` tool that persists knowledge across runs. Every lesson you save makes future runs faster, more reliable, and avoids repeated mistakes. Your lessons are loaded automatically into your prompt at startup — they are your memory.

**Save aggressively. When in doubt, save the lesson.**

## When to Save a Lesson

Save a lesson IMMEDIATELY when any of these happen:

1. **A command fails and you discover the correct syntax** — save the working syntax so you never fail the same way again.
2. **You retry something and find the right approach** — save what worked and why the first attempt failed.
3. **You learn how a process or workflow operates** — save the insight so future runs don't need to rediscover it.
4. **You discover a feed-specific quirk** — non-standard date formats, unusual HTML structure, rate limits, timeouts.
5. **You find a pattern or best practice through experience** — ordering of operations, optimal batch sizes, timing considerations.
6. **You encounter an error and figure out recovery** — save the error signature and what fixed it.
7. **A timeout value proves too short or too long** — save the correct value.
8. **You discover a dependency between operations** — e.g., "health check must run before retry".

## How to Save

Use `save_lesson` with:
- `reason`: Brief explanation of why you're saving this
- `agent_name`: Your agent name (`executor`, `parser`, `sentinel`, `fact_checker`)
- `category`: One of the standard categories below (or create a new one if none fit)
- `lesson`: The actual lesson — be **specific and actionable**, include exact commands, values, or steps

## Standard Categories
- **Command Syntax** — Correct command formats, flags, arguments, timeouts
- **Process Insights** — How workflows, pipelines, or operations actually behave
- **Feed Quirks** — Feed-specific behaviors, formats, or requirements
- **Best Practices** — Patterns that lead to better outcomes
- **Error Recovery** — How to handle specific error conditions
- **Timing & Thresholds** — Correct timeout values, batch sizes, intervals

## Rules
1. Save **one lesson per insight** — don't combine multiple discoveries into a single bullet.
2. Be specific — `timeout for fact-check should be 600s` is better than `use longer timeouts`.
3. Include the exact command or value when applicable.
4. Don't save obvious things that are already in your skills or documentation.
5. The tool is idempotent — calling it with the same lesson text twice is safe (it deduplicates).
