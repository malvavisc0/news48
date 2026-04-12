# Parser Agent Business Logic

```mermaid
flowchart TD
    Start([Parse Article]) --> Input[/Receive task:<br/>article_id, title,<br/>html_path, url/]
    Input --> ReadHTML[Read HTML file<br/>from provided path]
    ReadHTML --> TypeCheck{Non-standard type?}
    TypeCheck -->|Yes| Adapt[Adapt structure<br/>to article type]
    TypeCheck -->|No| Extract
    Adapt --> Extract
    ReadHTML --> Extract[Extract facts<br/>only from source]
    Extract --> Normalize[Normalize fields<br/>country codes, categories,<br/>sentiment, tags]
    Normalize --> QualityGate{Quality gate<br/>checks pass?}
    QualityGate -->|No| Fail[/Emit PARSE_FAIL<br/>reason_code/]
    QualityGate -->|Yes| Rewrite[Rewrite content<br/>simple, faithful English]
    Rewrite --> Stage[Write to /tmp/parsed_ID.txt]
    Stage --> Update[news48 articles update<br/>--content-file]
    Update --> Success[/Emit PARSE_OK<br/>fields list/]
    Success --> Stop([Stop])
    Fail --> Stop
```

## Always Active Skills

| Skill | Purpose |
|-------|---------|
| `read-source` | Always read HTML before extracting |
| `extract-facts` | Only explicit source evidence, no invented dates/entities |
| `normalize-fields` | ISO-2 countries, controlled categories, 8-140 char titles |
| `rewrite-content` | 2-4 paragraphs, plain language, no boilerplate |
| `enforce-quality` | Quality gate before update, fidelity checks |
| `stage-file` | Write to /tmp, use --content-file |
| `verify-result` | Emit PARSE_OK or PARSE_FAIL, caller detects via parsed_at |

## Conditional Skills

| Skill | Condition |
|-------|-----------|
| `adapt-to-type` | non_standard_type - Non-standard article types |
| `report-failure` | quality_gate_failure - Quality gate failure |

## Notes

- The parser itself emits `PARSE_OK` or `PARSE_FAIL`; the caller verifies the
  persisted result after the agent run.
- Failure reporting is an intra-run branch triggered after source reading or
  quality evaluation, not something that must be known at prompt composition.
