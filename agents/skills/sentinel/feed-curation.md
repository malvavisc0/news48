# Feed Curation Rules

## When to Delete a Feed

Delete a feed using `news48 feeds delete <id> --force` when:

1. **Permanently unreachable**: Feed has returned zero articles for 3+
   consecutive fetch cycles
2. **High download failure rate**: >80% of articles from this feed fail
   download over 48 hours
3. **High parse failure rate**: >60% of downloaded articles from this
   feed fail parsing (quality gate rejections, empty content, paywalled).
   Check with:
   ```bash
   news48 articles list --feed <domain> --status parse-failed --json
   news48 articles list --feed <domain> --status parsed --json
   ```
   If parse_failed / (parse_failed + parsed) > 60%, the feed is
   consistently producing unparseable content and should be removed.
4. **High negative fact-check rate**: >50% of parsed articles from this
   feed receive negative fact-check verdicts

## Before Deleting

1. Log the reason in `.lessons.md`
2. Send an email alert if email is configured
3. Use `news48 feeds info <id> --json` to confirm feed details
4. Use `news48 feeds delete <id> --force` to delete

## Safety Limits

- Never delete more than 3 feeds in a single cycle
- Always verify the feed ID before deletion
- If unsure, create a plan for human review instead of deleting
