# Feed Curation Rules

## Purpose

Use this skill to decide whether a problematic feed should be:

1. Reported for visibility only
2. Escalated into a human-review plan
3. Recommended for deletion with explicit evidence

Sentinel should not execute feed deletion directly unless another system policy explicitly authorizes it.

## Evidence Standard

Only recommend deletion when all of the following are true:

- The issue is provable using documented evidence commands.
- The observation window is long enough to rule out a transient spike.
- The denominator is large enough to make the rate meaningful.
- No equivalent active plan already exists to address the issue.

If any of those conditions are not met, create a review-oriented plan or report the concern without recommending deletion.

## When to Recommend Deletion

Recommend deletion only when one of these conditions is strongly supported:

1. **Permanently unreachable**: Feed has returned zero articles for 3+
   consecutive observed fetch opportunities **and** the evidence command set can directly support that conclusion.
2. **High download failure rate**: >80% of articles from this feed fail
   download over 48 hours, with at least 10 relevant articles in the window.
3. **High parse failure rate**: >60% of downloaded articles from this
   feed fail parsing (quality gate rejections, empty content, paywalled),
   with at least 10 relevant articles in the window.
   Check with:
   ```bash
   news48 articles list --feed <domain> --status parse-failed --json
   news48 articles list --feed <domain> --status parsed --json
   ```
   If parse_failed / (parse_failed + parsed) > 60%, the feed is
   consistently producing unparseable content and should be removed.
4. **High negative fact-check rate**: >50% of parsed articles from this
   feed receive negative fact-check verdicts, with at least 10 fact-checked
   articles in the window.

## When to Create a Review Plan Instead

Create a human-review plan rather than recommending deletion when:

- The rate breach exists but the sample size is too small.
- The evidence is indirect or aggregated and cannot prove a per-feed conclusion.
- The feed appears temporarily degraded rather than persistently harmful.
- Another active plan is already investigating or remediating the issue.

## Before Recommending Deletion

1. Use `news48 feeds info <id> --json` to confirm the feed identity.
2. Record the exact evidence, denominator, and observation window in the sentinel report.
3. Check `news48 plans list --json` to ensure the issue is not already being handled.
4. If the situation is novel, log the pattern using `save_lesson`.
5. Send an email alert if email is configured and the recommendation is high-impact.

## Safety Limits

- Never recommend deletion for more than 3 feeds in a single cycle.
- Always verify the feed ID before reporting a recommendation.
- If unsure, create a plan for human review instead of recommending deletion.
- Never infer per-feed conclusions from aggregate fetch data alone.
