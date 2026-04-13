# Fact-Check Business Logic

## Workflow

```mermaid
flowchart TD
    A[Start fact-check cycle] --> B[Claim fact-unchecked articles]
    B --> C{Articles claimed?}
    C -->|No| D[Return empty result]
    C -->|Yes| E[Extract claims from article]
    E --> F[Search for evidence]
    F --> G[Evaluate evidence]
    G --> H[Record verdict]
    H --> I[Release claim]
    I --> J[Return results]
```

## Skills

- `fc-extract-claims` — Extract key claims from the article
- `fc-search-evidence` — Search for supporting or refuting evidence
- `fc-record-verdict` — Record the fact-check verdict in the database
