# Homepage & Filter Improvements — Proposed Changes

## Problem Statement

1. **"All" pill is misleading**: Clicking "all" stays on `/` which shows only 35 stories out of potentially hundreds. Each category page (`/category/{slug}`) shows ALL articles with no limit, but the "all" view does not.
2. **No sentiment filter**: Articles already have a `sentiment` field (`positive`, `negative`, `neutral`) stored in the database, but there's no UI to filter by it anywhere on the website.

---

## Proposed Solution

### A. Homepage Redesign — Curated Preview (10 Stories)

Reduce the homepage story list from 35 to **10 stories**. This makes the homepage a curated "latest headlines" overview rather than a confusing halfway point between "all" and "nothing". Keep clusters and expiring sections as-is. Add a "view all stories →" link at the bottom of the story list.

### B. New `/all` Page — All Stories

Create a new route `/all` that shows ALL parsed stories with no limit (like category pages do today). This becomes the proper destination for the "all" navigation pill.

### C. Sentiment Filter Bar

Add a sentiment filter row on the homepage, `/all`, and category pages. Uses the same pill-style UI as the existing category nav. Filters via query parameters (`?sentiment=positive`), keeping it URL-based, bookmarkable, and JavaScript-free.

---

## URL Behavior After Changes

| URL | Behavior |
|-----|----------|
| `/` | Homepage: top 10 stories, clusters, expiring. Supports `?sentiment=` filter. |
| `/all` | All stories, no limit. Supports `?sentiment=` filter. |
| `/category/politics` | All politics stories. Supports `?sentiment=` filter. |
| `/article/123/slug` | Article detail (unchanged). |
| `/cluster/topic-slug` | Cluster detail (unchanged). |

---

## Files to Modify

| File | Changes |
|------|---------|
| `news48/web/app.py` | Add `/all` route. Update homepage to pass `sentiment` query param and limit to 10. Add sentiment filtering to existing category route. |
| `news48/web/templates/index.html` | Add sentiment filter bar. Reduce story section to 10. Add "view all stories" link. |
| `news48/web/templates/all.html` | **New** template — like category.html but for all stories. |
| `news48/web/templates/category.html` | Add sentiment filter bar. Add sentiment badge display in meta. |
| `news48/web/static/style.css` | Add `.sentiment-filter` and `.sentiment-pill` styles. |

---

## Mockups

### 1. Homepage (`/`) — With Sentiment Filter

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│  ai-verified news from the last 48 hours                        │
│  Rewritten in plain english, fact-check, and fast topic         │
│  discovery in one live feed                                     │
│                                                                 │
│  ● 42 live stories  18 verified  5 active clusters  12 sources  │
│  updated 12m ago                                                │
│                                                                 │
│  ── BROWSE BY CATEGORY ──────────────────────────────────       │
│  [ALL] [Politics] [Technology] [Health] [Business] [Science]    │
│                                                                 │
│  ── FILTER BY MOOD ──────────────────────────────────────       │
│  [▲ positive]  [— neutral]  [▼ negative]                        │
│                                                                 │
│  ── LATEST VERIFIED AND DEVELOPING STORIES ──────────────       │
│                                                                 │
│  [01] Headline of story one                                     │
│       Summary text here showing what this article is about...   │
│       Reuters  ·  12m ago  ·  ✓ Verified                        │
│       ▲ positive                                                │
│       46h left ████████████████████████                          │
│       Read more →  Open original source ↗                       │
│                                                                 │
│  [02] Headline of story two                                     │
│       Another summary showing article details...                │
│       BBC  ·  45m ago  ·  ✓ Verified                            │
│       — neutral                                                 │
│       44h left ████████████████████░░░░                          │
│       Read more →  Open original source ↗                       │
│                                                                 │
│  ... (10 stories total) ...                                     │
│                                                                 │
│                    → view all stories                            │
│                                                                 │
│  ── TOPIC CLUSTERS ──────────────────────────────────────       │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ climate summit    8 stories  ████████████░░░░░░░░        │    │
│  │ ai regulation     6 stories  █████████░░░░░░░░░░░        │    │
│  │ ...                                                     │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
│  ── STORIES LEAVING SOON ─────────────────────────────────      │
│  Story title here                                    2h left    │
│  Another expiring story                              3h left    │
│                                                                 │
│  news48 surfaces only the latest 48 hours of public stories     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 2. Homepage with Active Sentiment Filter (`/?sentiment=positive`)

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│  ai-verified news from the last 48 hours                        │
│  ...                                                            │
│                                                                 │
│  ── BROWSE BY CATEGORY ──────────────────────────────────       │
│  [ALL] [Politics] [Technology] [Health] [Business] [Science]    │
│                                                                 │
│  ── FILTER BY MOOD ──────────────────────────────────────       │
│  [▲ POSITIVE]  [— neutral]  [▼ negative]                        │
│   ▲ active ^                                                    │
│   (highlighted/dark background, same as active category pill)   │
│                                                                 │
│  ── LATEST VERIFIED AND DEVELOPING STORIES ──────────────       │
│                                                                 │
│  [01] Positive story headline here                              │
│       Summary of a positive news story...                       │
│       Reuters  ·  5m ago  ·  ✓ Verified                         │
│       ▲ positive                                                │
│       47h left ████████████████████████                          │
│       Read more →  Open original source ↗                       │
│                                                                 │
│  ... (filtered to positive only, up to 10) ...                  │
│                                                                 │
│                    → view all positive stories                   │
│                                                                 │
│  (clusters and expiring sections remain unchanged)              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 3. All Stories Page (`/all`)

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│  ← back to all stories                                          │
│                                                                 │
│  All Stories                                                    │
│  87 live stories across all categories                          │
│                                                                 │
│  ── BROWSE BY CATEGORY ──────────────────────────────────       │
│  [ALL*] [Politics] [Technology] [Health] [Business] [Science]   │
│   * ALL is active (highlighted)                                 │
│                                                                 │
│  ── FILTER BY MOOD ──────────────────────────────────────       │
│  [▲ positive]  [— neutral]  [▼ negative]                        │
│                                                                 │
│  ── ALL LIVE STORIES ────────────────────────────────────       │
│                                                                 │
│  [01] Headline one                                              │
│       Summary text...                                           │
│       Reuters  ·  12m ago  ·  ✓ Verified                        │
│       ▲ positive                                                │
│       46h left ████████████████████████                          │
│       Read more →  Open original source ↗                       │
│                                                                 │
│  [02] Headline two                                              │
│       ...                                                       │
│                                                                 │
│  [03] ... through to [87]                                       │
│       (no limit — all stories shown)                            │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 4. Category Page with Sentiment Filter (`/category/politics?sentiment=negative`)

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│  ← back to all stories                                          │
│                                                                 │
│  Politics                                                       │
│  12 live stories in Politics                                    │
│                                                                 │
│  ── BROWSE BY CATEGORY ──────────────────────────────────       │
│  [ALL] [Politics*] [Technology] [Health] [Business] [Science]   │
│   * Politics is active                                          │
│                                                                 │
│  ── FILTER BY MOOD ──────────────────────────────────────       │
│  [▲ positive]  [— neutral]  [▼ NEGATIVE]                        │
│                              ▼ active (highlighted)             │
│                                                                 │
│  ── LATEST POLITICS STORIES ─────────────────────────────       │
│                                                                 │
│  [01] Negative politics headline                                │
│       Summary...                                                │
│       AP  ·  30m ago                                            │
│       ▼ negative                                                │
│       Read more →  Open original source ↗                       │
│                                                                 │
│  ... (filtered: only negative politics stories) ...             │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Sentiment Filter Interaction Details

- **Clicking a sentiment pill** navigates to `?sentiment=positive` (or `neutral`, `negative`)
- **Clicking the active pill again** removes the filter (navigates to the same URL without `?sentiment=`)
- **Filter persists across category nav clicks**: If you're on `/?sentiment=positive` and click "Politics", you go to `/category/politics?sentiment=positive`
- **No JavaScript required**: All filtering is done server-side via query parameters
- **SEO-friendly**: Each filtered URL is a distinct, crawlable page

---

## CSS Design Notes

The sentiment filter bar reuses the existing `.category-nav` and `.category-pill` styling for visual consistency. Key additions:

```css
/* Sentiment filter — same layout as category nav */
.sentiment-filter {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    padding-bottom: 20px;
    border-bottom: 1px solid var(--rule);
}

/* Sentiment pills — identical to category pills */
.sentiment-pill {
    display: inline-flex;
    padding: 4px 10px;
    font-family: var(--font-label);
    font-size: 12px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--ink-light);
    border: 1px solid var(--rule);
    border-radius: 2px;
    text-decoration: none;
    transition: background 0.15s ease, color 0.15s ease;
}

/* Active sentiment pill — matches active category pill */
.sentiment-pill.active {
    background: var(--primary);
    border-color: var(--primary);
    color: var(--neutral);
    font-weight: 500;
}

/* Sentiment-specific active colors (optional enhancement) */
.sentiment-pill.active-positive {
    background: var(--verified);
    border-color: var(--verified);
    color: #FFFFFF;
}

.sentiment-pill.active-neutral {
    background: var(--ink-faint);
    border-color: var(--ink-faint);
    color: #FFFFFF;
}

.sentiment-pill.active-negative {
    background: var(--breaking);
    border-color: var(--breaking);
    color: #FFFFFF;
}
```

---

---

## CLI Integration — Expose Filters to Agents

### Current State

| CLI Command | `--sentiment` | `--category` | Notes |
|-------------|:---:|:---:|-------|
| `news48 search articles` | ✅ | ✅ | Already has both filters |
| `news48 articles list` | ❌ | ❌ | **Missing** — but `get_articles_paginated()` already supports both |

The `articles list` command currently accepts `--feed`, `--status`, `--language`, `--limit`, `--offset`. It does NOT expose `--sentiment` or `--category`, even though the underlying database function (`get_articles_paginated`) already has `sentiment` and `category` parameters.

### Proposed CLI Changes

Add `--sentiment` and `--category` options to `news48 articles list`:

```bash
# List all positive articles
news48 articles list --sentiment positive

# List all negative articles in technology category
news48 articles list --sentiment negative --category technology

# List neutral articles, JSON output (for agent consumption)
news48 articles list --sentiment neutral --json --limit 10

# Combine with existing filters
news48 articles list --status parsed --sentiment positive --category politics
```

### File to Modify

| File | Changes |
|------|---------|
| `news48/cli/commands/articles.py` | Add `--sentiment` and `--category` options to `list_articles()`. Pass them through to `get_articles_paginated()`. Include in output display. |

### CLI Mockup — `articles list` with new filters

```
$ news48 articles list --sentiment positive --category technology --limit 5

Articles: 5 of 12 (sentiment: positive, category: technology)
  [parsed] New AI chip achieves 3x performance improvement
    https://example.com/ai-chip
  [parsed] Renewable energy costs hit record low
    https://example.com/renewable
  [fact-checked] Open source project reaches 1M contributors
    https://example.com/oss
  [parsed] Quantum computing breakthrough announced
    https://example.com/quantum
  [parsed] Tech companies pledge carbon neutrality
    https://example.com/carbon
```

```
$ news48 articles list --sentiment negative --json --limit 3

{
  "feed_filter": null,
  "status_filter": null,
  "sentiment_filter": "negative",
  "category_filter": null,
  "total": 8,
  "limit": 3,
  "offset": 0,
  "articles": [
    {
      "id": 42,
      "title": "Data breach affects millions of users",
      "url": "https://example.com/breach",
      "feed_url": "https://example.com/feed.xml",
      "status": "parsed",
      "sentiment": "negative",
      "categories": "technology",
      "processing_status": null,
      "processing_owner": null,
      "processing_started_at": null,
      "created_at": "2026-04-24T18:30:00"
    }
  ]
}
```

---

## Implementation Checklist

### Web Changes
- [x] Reduce homepage stories from 35 → 10 in `app.py`
- [x] Add "view all stories →" link in `index.html`
- [x] Create `/all` route in `app.py` (queries all stories, accepts `?sentiment=`)
- [x] Create `all.html` template (based on `category.html`)
- [x] Add sentiment query parameter handling to homepage, `/all`, and `/category` routes
- [x] Add sentiment filter bar HTML to `index.html`, `all.html`, and `category.html`
- [x] Pass `active_sentiment` to all templates
- [x] Make category nav pills preserve `?sentiment=` param when navigating
- [x] Add `.sentiment-filter`, `.sentiment-pill` CSS classes
- [ ] Test all URL combinations (`/`, `/?sentiment=positive`, `/all`, `/all?sentiment=negative`, `/category/x?sentiment=neutral`)

### CLI Changes
- [x] Add `--sentiment` option to `news48 articles list`
- [x] Add `--category` option to `news48 articles list`
- [x] Pass `sentiment` and `category` to `get_articles_paginated()`
- [x] Include `sentiment_filter` and `category_filter` in JSON output
- [x] Show sentiment/category in human-readable output header
- [ ] Test CLI filter combinations

---

## Code Review Findings

### 🐛 Bug: Category page 404s when sentiment filter returns zero results

**File:** [`category_detail()`](news48/web/app.py:384) — lines 397-401

```python
articles, total = get_articles_by_category(
    category_slug, hours=48, limit=None, parsed=True, sentiment=sentiment
)
if not articles:
    raise HTTPException(status_code=404, detail="Category not found")
```

If a valid category like `politics` exists but has zero articles matching the sentiment filter, the route returns **HTTP 404**. Example: `/category/politics?sentiment=positive` returns "Category not found" when there are no positive politics stories — even though the category itself exists.

**Fix:** Split the check. First verify the category exists (query without sentiment), then apply the sentiment filter. Or: only 404 when `total == 0 and sentiment is None`, and show an empty state otherwise.

---

### ⚠️ Gap 1: `/all` not included in sitemap

**File:** [`sitemap()`](news48/web/app.py:480) — lines 496-523

The sitemap generation includes `/`, `/category/*`, `/cluster/*`, and individual articles, but does NOT include the new `/all` route. Since the proposal states each filtered URL should be SEO-friendly and crawlable, `/all` should be in the sitemap.

**Fix:** Add `/all` to the `extra_urls` list in the sitemap route:
```python
extra_urls.append({
    "canonical_url": build_canonical_url(site_url, "/all"),
    "priority": "0.9",
    "changefreq": "hourly",
})
```

---

### ⚠️ Gap 2: `article.html` and `cluster.html` still link "all" pill to `/` instead of `/all`

**Files:**
- [`article.html`](news48/web/templates/article.html:172) — line 172: `<a href="/" class="category-pill ...">all</a>`
- [`cluster.html`](news48/web/templates/cluster.html:25) — line 25: `<a href="/" class="category-pill ...">all</a>`

These were not listed in the proposal's "Files to Modify" table, but they both contain category navigation with an "all" pill that still points to `/` instead of `/all`. After this change, clicking "all" from an article detail page takes the user to the homepage (10 stories) rather than the new all-stories page — breaking the mental model.

**Fix:** Update both templates to link to `/all` and add sentiment preservation if desired. Note: these routes currently don't pass `active_sentiment` to the template context, so sentiment preservation would also need a backend change if desired.

---

### ⚠️ Gap 3: FastAPI `Query(regex=...)` is deprecated — use `pattern=`

**File:** [`app.py`](news48/web/app.py:90) — lines 90, 311, 388

```python
sentiment: str | None = Query(None, regex="^(positive|negative|neutral)$")
```

Since FastAPI is unpinned in [`pyproject.toml`](pyproject.toml:36), any version can be installed. In FastAPI 0.100+ (Pydantic v2), the `regex` parameter on `Query()` was deprecated in favor of `pattern`. With recent versions this will emit deprecation warnings and may break in future releases.

**Fix:** Change `regex=` to `pattern=` on all three route definitions:
```python
sentiment: str | None = Query(None, pattern="^(positive|negative|neutral)$")
```

---

### 📝 Minor 1: Proposal CSS differs from implemented CSS (cosmetic, not a bug)

The proposal's CSS section (lines 222-273) specifies `color: #FFFFFF` for active sentiment pills. The actual implementation in [`style.css`](news48/web/static/style.css:374) correctly uses `color: var(--verified-fg)` and `color: var(--surface)` — which is better since it respects the design token system. The doc should be updated to match the implementation.

---

### 📝 Minor 2: Filtered count in tagline could be clearer

In [`all.html`](news48/web/templates/all.html:20) and [`category.html`](news48/web/templates/category.html:20), the tagline shows `{{ total }} live stories...`. When a sentiment filter is active, `total` reflects the **filtered** count. For example: "3 live stories in Politics" when there are actually 15, but only 3 are negative. This is technically correct but could confuse users who don't notice the active filter.

**Optional enhancement:** When a sentiment filter is active, append the filter label: `3 negative stories in Politics` or `3 of 15 stories in Politics (negative)`.

---

### 📝 Minor 3: Doc checklist is partially stale

The implementation checklist at the bottom of the proposal still shows all items as `[ ]` unchecked, but from the code review, every single web and CLI item has already been implemented. The checklist should be updated to reflect the current state.

---

## Review Summary

| Severity | Finding | Status |
|----------|---------|--------|
| 🐛 Bug | Category page 404s on empty sentiment-filtered results | ✅ Fixed |
| ⚠️ Gap | `/all` missing from sitemap | ✅ Fixed |
| ⚠️ Gap | `article.html` and `cluster.html` "all" pill still points to `/` | ✅ Fixed |
| ⚠️ Gap | `Query(regex=...)` deprecated in FastAPI 0.100+ | ✅ Fixed |
| 📝 Minor | Proposal CSS vs actual CSS token mismatch | Doc-only (no code impact) |
| 📝 Minor | Filtered count in tagline could be clearer | Optional UX enhancement |
| 📝 Minor | Checklist shows unchecked but code is implemented | ✅ Fixed |

**Overall assessment:** The implementation is solid and closely follows the proposal. All bugs and gaps have been fixed. No data corruption or security issues found.
