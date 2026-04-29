# Skill: Review parsed output before finalizing

## Scope
Always active — parser must re-read its own output and actively scan for garbage before persisting.

## Purpose
Source articles often contain non-article content embedded within or appended to the actual text: navigation menus, "related articles" blocks, sidebar content, ad copy, author bios, social prompts, comment section teasers, and other UI artifacts. Extraction and rewriting instructions mitigate this, but a dedicated review pass catches anything that slipped through.

## When to Run
After staging content to the temp file and **before** running `news48 articles update`. This is a mandatory quality gate that must pass before any persistence attempt.

## Procedure

### Step 1: Re-read the staged file
Use `read_file` on `/tmp/parsed_ARTICLEID.txt` to read back exactly what will be persisted.

### Step 2: Scan content for garbage patterns
Inspect every paragraph of the staged content for the following non-article patterns. Any match is a failure that must be cleaned before persisting.

**Navigation / Menu artifacts:**
- Menu items or site navigation text (e.g., "Home", "About Us", "Contact", "Privacy Policy", "Terms of Service", "Site Map")
- Breadcrumb trails or category navigation
- Hamburger/mobile menu labels
- Header or footer boilerplate

**"Related articles" / Recommendation blocks:**
- "Related articles", "Related stories", "You may also like", "More from", "Trending now", "Popular stories", "Recommended for you", "Also read", "Read also", "More on this topic", "In other news"
- Any block that lists other article titles or links — these are recommendation engine output, not part of the article

**Social / Engagement prompts:**
- "Follow us", "Share this article", "Share on Twitter/Facebook", "Tweet this", "Like us on Facebook"
- "Subscribe to our newsletter", "Sign up for updates", "Get the newsletter"
- "Leave a comment", "Join the discussion", "What do you think?"

**Advertising / Sponsor content:**
- "Sponsored", "Advertisement", "Promoted content", "Paid partnership"
- Ad copy, promotional text, or product mentions that are clearly not editorial

**Boilerplate / Legal:**
- Copyright notices (e.g., "© 2024", "All rights reserved")
- "This article was originally published on...", "Reprinted with permission"
- Terms of use, privacy policy references

**Truncation / Paywall indicators:**
- "...", "Continue reading", "Read more", "Subscribe to read", "Sign in to continue"
- "This content is for subscribers only", "To read the full article"

**Other non-article content:**
- Author bio blocks ("John Smith is a senior reporter covering...")
- Newsletter signup forms or email capture prompts
- Comment sections or comment previews
- Poll or survey content unrelated to the article
- Table of contents or "jump to" navigation for the same page

### Step 3: Scan title and summary for quality
- Title must be non-empty, factual, 8–140 characters, sentence case, and clearly different from the source title
- Summary must be 1–3 sentences, 80–420 characters, not equal to the title, and not starting with meta-references
- Neither title nor summary may contain HTML tags, markdown syntax, or navigation artifacts

### Step 4: Clean if garbage found
If any garbage pattern is detected in the content:
1. Remove the garbage paragraph(s) or phrase(s) entirely — do not paraphrase garbage
2. If removing garbage drops the content below 1,200 characters or below 3 paragraphs, the parse must be failed: `news48 articles fail ARTICLEID --error "parse.garbage_content: Content contained embedded garbage (menus/related articles/navigation) and cleanup reduced content below quality thresholds" --json`
3. If content still meets thresholds after cleanup, re-stage the cleaned content to the temp file and proceed

If garbage is found in title or summary:
1. Rewrite the affected field to remove the garbage
2. Re-run the title and summary quality checks

### Step 5: Final confirmation
After cleaning, confirm:
- [ ] Content is 1,200–10,000 characters across 3–15 substantive paragraphs
- [ ] Each paragraph is at least 150 characters and carries genuine article content
- [ ] No paragraph contains any garbage pattern from the list above
- [ ] Title and summary are clean and meet all quality standards
- [ ] No HTML tags, markdown syntax, or formatting artifacts in any field

Only after this confirmation passes should the parser proceed to `news48 articles update`.

## Error Code
Use `parse.garbage_content` when content contained embedded non-article garbage that had to be cleaned, and the cleanup caused a quality threshold violation.

## Anti-Pattern: Skipping the Review
Never emit `PARSE_OK` without reading back the staged file first. The parser must not trust that its rewrite output is clean — it must verify by reading the actual staged content.