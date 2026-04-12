# Skill: Monitor disk space usage

## Scope
Always active — monitor must check disk space to prevent agent failures.

## Rules
1. **Check disk space**: Run `df -h /tmp` and `df -h .` at the start of each monitoring cycle.
2. **Thresholds**:
   - `WARNING` if any monitored filesystem is > 80% full
   - `CRITICAL` if any monitored filesystem is > 90% full
3. **Include in report**: Add disk space metrics to the monitor report under `metrics.disk_space` with keys `tmp_percent` and `root_percent`.
4. **Recommendations**: When disk space is low, recommend:
   - Running retention cleanup to free space
   - Clearing `/tmp` of old wave logs and parsed files
   - Investigating large files in the project directory
5. **Error code**: Use `sys.disk_space` when reporting disk-related failures.

## Cleanup Actions
When disk space is CRITICAL:
- Recommend `news48 cleanup run --json` to remove expired articles
- Recommend `find /tmp -name '*.log' -mtime +1 -delete` to clear old logs
- Recommend `find /tmp -name 'parsed_*' -mtime +1 -delete` to clear old parsed files
