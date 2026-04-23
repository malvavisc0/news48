# Skill: Save operational lessons only

## Scope
Always active — every agent MUST save only reusable operational lessons.

## Why This Matters
You have a `save_lesson` tool that persists knowledge across runs. Every lesson you save makes future runs faster, more reliable, and avoids repeated mistakes. Your lessons are loaded automatically into your prompt at startup — they are your memory.

Save lessons eagerly, but only when they improve future system operation.

## When to Save a Lesson

Save a lesson when any of these happen:

1. **A command fails and you discover the correct syntax** — save the working syntax so you never fail the same way again.
1a. **You use `news48 --help` or subcommand help to confirm the real CLI shape** — save the useful syntax only if it corrected uncertainty or prevented a mistake.
2. **You retry something and find the right approach** — save what worked and why the first attempt failed.
3. **You learn how a process or workflow operates through execution** — save the insight so future runs don't need to rediscover it.
4. **You discover a feed-specific quirk** — non-standard date formats, unusual HTML structure, rate limits, timeouts.
5. **You find a pattern or best practice through experience** — ordering of operations, optimal batch sizes, timing considerations.
6. **You encounter an error and figure out recovery** — save the error signature and what fixed it.
7. **A timeout value proves too short or too long** — save the correct value.
8. **You discover a dependency between operations** — e.g., "health check must run before retry".

## Do Not Save

Never save any of these as lessons:

- article-specific facts, verdicts, claim lists, or summaries
- fact-check outputs that belong in article records
- routine healthy/unhealthy system snapshots
- one-run status reports with no reusable operational rule
- anything already captured by the article, plan, or report output itself

## Reuse Test

Before saving, both must be true:

1. You learned something about operating the system, recovering from errors, or handling a recurring source/workflow pattern.
2. The lesson would help on a different future run, article, plan, or feed.

If either answer is no, do not save a lesson.

## How to Save

Use `save_lesson` with:
- `reason`: Brief explanation of why you're saving this
- `agent_name`: Your agent name (`executor`, `parser`, `sentinel`, `fact_checker`)
- `category`: One of the standard categories below (or create a new one if none fit)
- `lesson`: The actual lesson — be **specific and actionable**, include exact commands, values, or steps, and describe an operational rule rather than run output

Safe shell inspection commands are also valid lesson sources when they reveal a reusable operating rule.

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
5. Prefer the form `when X happens, do Y because Z`.
6. Do not save task results or content conclusions as lessons.
7. The tool is idempotent — calling it with the same lesson text twice is safe (it deduplicates).
