# Parser Agent Business Logic

```mermaid
flowchart TD
    Start([Parse Article]) --> Input[/Receive task:<br/>article_id, title,<br/>html_path, url/]
    Input --> ReadContent[Read content file<br/>from provided path]
    ReadContent --> TypeCheck{Non-standard type?}
    TypeCheck -->|Yes| Adapt[Adapt structure<br/>to article type]
    TypeCheck -->|No| Extract
    Adapt --> Extract[Extract facts<br/>only from source<br/>with full depth]
    Extract --> Normalize[Normalize fields<br/>country codes, categories,<br/>sentiment, tags]
    Normalize --> Rewrite[Rewrite content<br/>original language,<br/>substantive depth]
    Rewrite --> OriginalityCheck{Originality<br/>check pass?}
    OriginalityCheck -->|No| FailCopy[/Emit PARSE_FAIL<br/>parse.verbatim_copy/]
    OriginalityCheck -->|Yes| DepthCheck{Depth<br/>check pass?}
    DepthCheck -->|No| FailDepth[/Emit PARSE_FAIL<br/>parse.shallow_content/]
    DepthCheck -->|Yes| TitleCheck{Title<br/>transformed?}
    TitleCheck -->|No| FailTitle[/Emit PARSE_FAIL<br/>parse.unchanged_title/]
    TitleCheck -->|Yes| QualityGate{Quality gate<br/>checks pass?}
    QualityGate -->|No| Fail[/Emit PARSE_FAIL<br/>reason_code/]
    QualityGate -->|Yes| Stage[Write to /tmp/parsed_ID.txt]
    Stage --> Update[uv run news48 articles update<br/>--content-file]
    Update --> Success[/Emit PARSE_OK<br/>fields list/]
    Success --> Stop([Stop])
    FailCopy --> Stop
    FailDepth --> Stop
    FailTitle --> Stop
    Fail --> Stop
```

## Always Active Skills

| Skill | Purpose |
|-------|---------|
| `read-source` | Always read HTML before extracting |
| `extract-facts` | Extract all significant facts with full depth — not just headline claims |
| `normalize-fields` | ISO-2 countries, controlled categories, 8-140 char titles |
| `rewrite-content` | Fully original rewrite, 3+ paragraphs, 1200+ chars, no verbatim copying |
| `enforce-quality` | Quality gate before update — originality, depth, title-change, fidelity checks |
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
- Three dedicated validation checks run before the general quality gate:
  originality (no verbatim copying), depth (1200+ chars, 3+ paragraphs), and
  title transformation (title must differ from source).
- Failure reporting is an intra-run branch triggered after source reading or
  quality evaluation, not something that must be known at prompt composition.
- Successful persistence uses `uv run news48 articles update ... --json`.
- Failure persistence uses `uv run news48 articles fail ... --error ... --json`.
