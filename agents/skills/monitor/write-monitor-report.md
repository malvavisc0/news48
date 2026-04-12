# Skill: Write monitor report to file

## Scope
Always active — monitor must persist each cycle's report so the Planner can read it.

## Rules
1. After generating the full report (Steps 1–5 of the monitoring cycle), write the report to a file using `run_shell_command`:
   ```bash
   mkdir -p .monitor && cat > .monitor/latest-report.json << 'REPORT_EOF'
   {JSON content}
   REPORT_EOF
   ```
2. The JSON file must contain these top-level keys:
   - `timestamp`: ISO 8601 UTC timestamp of the cycle
   - `status`: `HEALTHY`, `WARNING`, or `CRITICAL`
   - `metrics`: object with the key metrics gathered in Step 1
   - `alerts`: array of alert objects, each with `severity`, `metric`, `description`, `evidence`
   - `recommendations`: array of recommended actions for Planner/Executor
3. Always overwrite the previous report — only the latest report is kept.
4. Do not skip this step even when status is HEALTHY — the Planner needs to know the system is healthy.
5. If the write fails, include a note in the report output but do not abort the cycle.