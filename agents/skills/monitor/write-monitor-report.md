# Skill: Write monitor report to file

## Scope
Always active — monitor must persist each cycle's report so the Planner can read it.

## Rules
1. After generating the full report (Steps 1–5 of the monitoring cycle), write the report to a file using Python to avoid heredoc injection vulnerabilities:
   ```bash
   python3 -c "
import json, os
os.makedirs('.monitor', exist_ok=True)
report = json.loads('''{JSON content}''')
with open('.monitor/latest-report.json', 'w') as f:
    json.dump(report, f, indent=2)
"
   ```
   Alternatively, if using shell heredoc is required, use a UUID-based delimiter that cannot appear in JSON content:
   ```bash
   mkdir -p .monitor && cat > .monitor/latest-report.json << 'EOF_4a7b9c2d'
   {JSON content}
   EOF_4a7b9c2d
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