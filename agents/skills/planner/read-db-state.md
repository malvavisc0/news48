# Skill: Ground plans in database state

## Trigger
Always active — planner must ground plans in the actual persisted schema and derived statuses.

## Core Schema
- `feeds` stores feed identity and freshness fields such as `url`, `title`, `last_fetched_at`, `language`, and `category`.
- `fetches` stores aggregate fetch-run outcomes such as `started_at`, `completed_at`, `status`, `feeds_fetched`, and `articles_found`.
- `articles` stores lifecycle fields across multiple columns including `content`, `parsed_at`, `download_failed`, `parse_failed`, `fact_check_status`, and processing-claim fields.

## Rules
1. Do not assume a single stored article status column exists.
2. Treat article states exposed by the CLI as derived views over multiple fields.
3. Write success conditions only for states that can be observed through documented CLI output or known persisted fields.
4. Distinguish durable persisted state from transient run output.
5. Do not invent feed-health or article-health fields that are not in the schema.
6. Do not express per-feed success using aggregate fetch-run fields that only exist at the `fetches` level.
7. When a condition mixes entity-level claims with run-level aggregates, treat it as suspect and rewrite it.

## Planning Implications
- Feed freshness is evidenced by `last_fetched_at`, not by assuming every feed is fetchable.
- Article backlog should be reasoned from derived statuses such as `empty`, `downloaded`, `parsed`, `download-failed`, and `parse-failed`.
- Fact-check coverage depends on `fact_check_status`, not only on parsing completion.
- Concurrency and in-progress work depend on `processing_status`, `processing_owner`, and `processing_started_at`.

## Forbidden Assumptions
- `All feeds can eventually leave never_fetched`
- `Every parsed article is fact-check eligible`
- `Articles have one canonical status column in the database`
- `A plan condition is valid even if no CLI output can prove it`
- `Per-feed article insertion can be proven directly from aggregate fetches.articles_found`
