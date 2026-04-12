# Skill: Write realistic success conditions

## Scope
Always active — planner must define success conditions before steps.

## Rules
1. Always define `success_conditions` before writing plan steps.
2. Conditions are **outcome statements**, not activity statements.
3. Include 2-5 conditions per plan.
4. Each condition must map to observable CLI evidence and to real persisted or derived system state.
5. Use percentages for rates (`>= 75%`, `>= 90%`) and bounded coverage for external operations. Never require 100% success for external resources.
6. Zero-presence checks (`No X remain in Y`) are only valid for **internal** state transitions the system fully controls. Never use them for outcomes that depend on external servers.
7. Do not use a condition that depends on a field, status, or metric the system does not actually expose.
8. Before finalizing a plan, review each condition and remove any one that fails the self-check below.
9. Treat the bad-pattern list as illustrative, not exhaustive.
10. If execution uses batched commands such as `news48 download --limit`, write conditions that remain valid across repeated calls and do not imply one batch clears the whole backlog.

## Self-Check Before Plan Creation
For each condition, verify all of the following:
- Which condition type is it: external threshold, internal completion, or verification-only?
- Is this an outcome rather than an action?
- Can the executor prove it with documented CLI evidence?
- Does it map to real schema fields or documented derived statuses?
- If external systems are involved, is it threshold-based rather than absolute?
- Does it avoid merely restating the current state or describing an observational no-op?
- Is it semantically equivalent to a forbidden pattern even if the wording is different?

If any answer is no, rewrite or remove the condition before creating the plan.

## Semantic Rejection Rules
Reject a condition if it does any of the following, regardless of wording:
- Demands perfect completion for work that depends on external systems.
- Uses aggregate evidence to prove per-entity outcomes.
- Assumes a derived label is a guaranteed persisted field.
- Restates present state instead of defining meaningful work completion.
- Claims the absence of failures in a domain where unreachable external resources are expected.

## Condition Types
- **External threshold**: remote systems involved; use rate or bounded coverage.
- **Internal completion**: purely local state; zero-presence or exact completion is allowed.
- **Verification-only**: health, integrity, or queue coherence checks backed by read-only evidence.

## Good Patterns
- `≥90% of target feeds have last_fetched_at within last 120 minutes`
- `No articles remain in empty status` (internal: coverage plan ensures download plans exist)
- `Download success rate >= 75%`
- `Eligible empty backlog for arstechnica.com is reduced to zero after repeated download batches`
- `No pending plans remain blocked by failed parent plans`

## Bad Patterns
- ~~`Run fetch command`~~ (activity)
- ~~`Try to improve downloads`~~ (vague)
- ~~`Check things look healthy`~~ (not measurable)
- ~~`All 55 feeds have last_fetched_at within 120 minutes`~~ (assumes 100% external success)
- ~~`No feeds remain in never_fetched status`~~ (external servers may be permanently unreachable)
- ~~`Every article is in parsed status because parsing finished`~~ (derived status must be evidenced, not assumed)
- ~~`System reports zero feeds, zero articles, and zero plans`~~ (observational no-op, not meaningful work)
- ~~`Every seeded feed has been fetched successfully at least once`~~ (same forbidden meaning as zero never-fetched tolerance)
- ~~`Fetch run shows articles_found > 0 for each feed`~~ (uses aggregate evidence as if it were per-feed proof)
- ~~`All 646 empty articles for a feed are downloaded after one download call`~~ (ignores batching and command limits)
