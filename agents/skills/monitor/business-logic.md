# Monitor Agent Business Logic

```mermaid
flowchart TD
    Start([Start Monitoring Cycle]) --> Gather[Gather Evidence]
    Gather --> Evidence[Run evidence commands:<br/>stats, cleanup health,<br/>cleanup status,<br/>feeds list, fetches list,<br/>articles list fact-unchecked,<br/>check disk space]
    Evidence --> FactCheckReview[Review fact-check backlog<br/>fact-unchecked + fact-checked]
    FactCheckReview --> Compute[Compute rates<br/>download_failures/(download_failures+parse_backlog+parsed)<br/>parse_failures/(parse_failures+parsed)]
    Compute --> Thresholds[Compare proved metrics<br/>against thresholds]
    Thresholds --> Classify{Classify status}
    Classify -->|Critical breach| CRITICAL{CRITICAL}
    Classify -->|Warning only| WARNING{WARNING}
    Classify -->|No breach| HEALTHY{HEALTHY}
    CRITICAL --> Alerts[Generate alerts<br/>from breaches]
    WARNING --> Alerts
    HEALTHY --> Report[/Generate report/]
    Alerts --> Recommend[Recommend actions<br/>for planner/executor]
    Recommend --> Report
    Report --> Format[1. Overall Status<br/>2. Metrics Summary<br/>3. Alerts<br/>4. Recommendations]
    Format --> PersistReport[Write report to<br/>.monitor/latest-report.json]
    PersistReport --> PersistMetrics[Write metrics to<br/>.metrics/timestamp.json]
    PersistMetrics --> Email{status + email<br/>configured?}
    Email -->|WARNING| SendEmail[send_email<br/>Normal report]
    Email -->|CRITICAL| SendUrgent[send_email<br/>[URGENT] subject]
    Email -->|HEALTHY or<br/>not configured| Skip[/Skip email/]
    SendEmail --> Done([Done])
    SendUrgent --> Done
    Skip --> Done
```

## Always Active Skills

| Skill | Purpose |
|-------|---------|
| `begin-monitoring-cycle` | 8-step workflow: evidence → rates → thresholds → classify → report → persist report → persist metrics → email |
| `evaluate-thresholds` | Compare metrics; record "insufficient sample" when denominator=0 or metric unavailable |
| `compute-rates` | Use only proved stats fields; undefined (0-denominator) rates recorded as null |
| `review-fact-check` | fact-unchecked backlog, completions in 24h, oldest item age |
| `check-disk-space` | Check /tmp and project directory usage, raise alerts at 80%/90% |
| `thresholds` | Canonical threshold table and classification rules |
| `write-monitor-report` | Persist report to `.monitor/latest-report.json` for Planner to read |
| `write-metrics-history` | Persist cycle metrics to `.metrics/` for trend analysis |

## Conditional Skills

| Skill | Condition |
|-------|-----------|
| `generate-alerts` | threshold_breached - Threshold is breached |
| `recommend-actions` | alerts_exist - Alerts exist |
| `send-email` | status:WARNING|CRITICAL - Status is WARNING or CRITICAL |

## Notes

- Monitor preloads the alerting branches because threshold breaches are only
  discovered after evidence gathering.
- The `send-email` branch should be used only when email is configured and the
  final status is `WARNING` or `CRITICAL`.
