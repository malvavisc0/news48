# Feed Curation Rules

## When to Delete a Feed

Delete a feed using `news48 feeds delete <id> --force` when:

1. **Permanently unreachable**: Feed has returned zero articles for 3+
   consecutive fetch cycles
2. **High download failure rate**: >80% of articles from this feed fail
   download over 48 hours
3. **High negative fact-check rate**: >50% of parsed articles from this
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
