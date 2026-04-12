# Skill: Write metrics history file

## Scope
Always active — monitor must persist cycle metrics for trend analysis.

## Rules
1. After completing the monitoring cycle (after Step 7: Send Email), write a timestamped metrics file using `run_shell_command`:
   ```bash
   mkdir -p .metrics && cat > ".metrics/$(date -u +%Y-%m-%dT%H-%M-%S).json" << 'EOF'
   {JSON content}
   EOF
   ```
2. The JSON file must contain these top-level keys:
   - `timestamp`: ISO 8601 UTC timestamp of the cycle
   - `status`: `HEALTHY`, `WARNING`, or `CRITICAL`
   - `metrics`: object with key numeric metrics from `news48 stats --json`
   - `alerts_count`: number of alerts generated
   - `recommendations_count`: number of recommendations generated
3. Keep only the last 100 metrics files. Delete older files using:
   ```bash
   ls -t .metrics/*.json | tail -n +101 | xargs -r rm
   ```
4. This enables the Planner and future cycles to detect trends (e.g., backlog growing over time, failure rates improving or worsening).
5. If the write fails, include a note in the report output but do not abort the cycle.