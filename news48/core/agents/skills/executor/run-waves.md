# Skill: Execute work in waves

## Scope
Active when plan family is fetch or download. (Parse-family plans do not use waves — the Parser agent processes articles individually.)

## Rules
1. Use background processes (`&` + `wait`) for fetch and download with multiple domains.
2. Group consecutive same-type steps into parallel waves of **at most 4** processes.
3. If more than 4 steps of same type, split into multiple waves.
4. For single targeted operation (single article/domain), synchronous execution is allowed.
5. For large per-feed download backlog, run repeated waves as needed; one wave is not proof that the feed backlog is cleared.
6. When a command supports `--limit`, choose a limit that matches the plan scope and continue issuing calls until evidence shows the target state or a verified stall.

## Wave Execution with Failure Detection
After `wait`, check exit codes of each background process:

```bash
news48 download --feed arstechnica.com --json > /tmp/dl_ars.log 2>&1 &
PID_ARS=$!
news48 download --feed theverge.com --json > /tmp/dl_verge.log 2>&1 &
PID_VERGE=$!
news48 download --feed example.com --json > /tmp/dl_ex.log 2>&1 &
PID_EX=$!
wait $PID_ARS; EXIT_ARS=$?
wait $PID_VERGE; EXIT_VERGE=$?
wait $PID_EX; EXIT_EX=$?

# Check each exit code individually
if [ $EXIT_ARS -ne 0 ]; then echo "FAILED: arstechnica.com"; cat /tmp/dl_ars.log; fi
if [ $EXIT_VERGE -ne 0 ]; then echo "FAILED: theverge.com"; cat /tmp/dl_verge.log; fi
if [ $EXIT_EX -ne 0 ]; then echo "FAILED: example.com"; cat /tmp/dl_ex.log; fi

echo "WAVE_DONE"
```

- If any individual process fails, mark only that step as failed — do not fail the entire plan.
- Continue executing remaining steps in the plan after wave completion.
- Log which specific domains failed for planner visibility.
