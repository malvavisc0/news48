# Skill: Run plan commands safely

## Scope
Always active — executor transforms plan prose into CLI commands.

## Rules
1. Pass `timeout` as a **tool parameter**, not a CLI flag.
   - Correct: `run_shell_command(command='news48 download ...', timeout=300)`
   - Wrong: `run_shell_command(command='news48 download ... --timeout=300')`
2. Timeout guidance:
   - Single targeted operation: `timeout=180`
   - Download waves: `timeout=300`
   - Fact-check (with web search): `timeout=600`
3. Increase timeout only when logs show active progress.
4. Always run CLI commands as `news48 ...` and pass `--json` whenever the command supports it.
5. Use `--feed` for per-domain steps; omit when plan scope requires broader execution.
6. When `news48 download` is used for feed-scoped backlog work, pass `--limit` explicitly when needed and repeat the command until the plan outcome is reached, no eligible backlog remains, or progress stalls.
7. Do not assume one command invocation satisfies a large backlog just because the command succeeded.
8. If a plan step does not contain an executable command and no loaded skill provides one, fail the step instead of improvising.
