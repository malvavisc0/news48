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
   - Parse waves: `timeout=600`
3. Increase timeout only when logs show active progress.
4. Always pass `--json` to every `news48` command.
5. Use `--feed` for per-domain steps; omit when plan scope requires broader execution.
