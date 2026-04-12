# Skill: Execute work in waves

## Trigger
Active when plan family is fetch, download, or parse.

## Rules
1. Use background processes (`&` + `wait`) for fetch, download, parse with multiple domains.
2. Group consecutive same-type steps into parallel waves of **at most 4** processes.
3. If more than 4 steps of same type, split into multiple waves.
4. For single targeted operation (single article/domain), synchronous execution is allowed.

## Wave Example
```bash
news48 download --feed arstechnica.com --json > /tmp/dl_ars.log 2>&1 &
news48 download --feed theverge.com --json > /tmp/dl_verge.log 2>&1 &
news48 download --feed example.com --json > /tmp/dl_ex.log 2>&1 &
wait
echo "WAVE_DONE"
```
