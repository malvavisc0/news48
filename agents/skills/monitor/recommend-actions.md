# Skill: recommend-actions

## Trigger
Conditional — active when alerts exist.

## Rules
Map observed issues to concrete next commands.

### Database Size Warning
1. Check retention: `news48 cleanup status --json`
2. Recommend: `news48 cleanup run`

### Feed Stale Warning
1. List stale feeds: `news48 feeds list --json`
2. Recommend autonomous remediation via planner/executor

### High Failure Rate
1. List failed: `news48 articles list --status download-failed --json`
2. Group by domain
3. Recommend retry or investigation

### Backlog Pattern
1. Count by status: `news48 stats --json`
2. Identify bottleneck stage
3. Recommend download or parse cycle
