# news48 MCP Tools

news48 exposes an MCP server that gives AI agents access to **live, fact-checked news from the last 48 hours**. It provides 6 tools designed around the questions an agent actually needs to answer.

## Why MCP?

Agents that need current event context face a hard problem: news APIs return raw data that requires heavy processing, and scraping is fragile. news48 handles the entire pipeline — fetching, parsing, deduplication, LLM-powered summarization, and automated fact-checking — and exposes the results through MCP so agents can consume structured, verified news with zero preprocessing.

## Tools

| Tool | Purpose | Typical Question |
|------|---------|-----------------|
| `get_briefing` | News overview | "What's happening right now?" |
| `search_news` | Full-text search | "Find articles about X" |
| `get_article` | Deep dive | "Tell me more about this" |
| `browse_category` | Category exploration | "Show me tech news" |
| `list_categories` | Discovery | "What topics exist?" |
| `list_countries` | Country discovery | "Which countries are in the news?" |

### `get_briefing`

The starting point. Returns a structured briefing with top stories, trending topic clusters, and breaking news in a single call. Designed to give an agent full situational awareness without needing to make multiple requests.

```
→ get_briefing(hours=48, limit=10)
```

Returns `top_stories` (deduplicated, ranked by freshness and parse quality), `trending_topics` (tag clusters with article counts and top titles), `breaking` (articles flagged as breaking news), and `stats` (total stories, source count, verified count).

**Use it when:** initializing a session, generating a summary, answering "what's going on?", or before drilling into specifics.

### `search_news`

Full-text search with optional filters. Powered by a full-text index across title, summary, content, tags, and categories.

```
→ search_news(query="climate change", sentiment="negative", limit=10)
```

All parameters except `query` are optional. Use `hours` to control the time window, `sentiment` to filter by tone, `category` to narrow to a topic area, and `country` to filter by country code (e.g., `"us"`, `"gb"`, `"de"`). Results are ranked by relevance.

**Use it when:** researching a topic, finding source articles for fact-checking, or answering a specific question about recent events.

### `get_article`

Full article content with fact-check claims and related coverage from other sources. This is the deep-dive tool — call it after finding an article through `search_news` or `get_briefing`.

```
→ get_article(article_id=123, include_related=true)
```

Returns the complete article (rewritten summary, full content, metadata), all extracted claims with their fact-check verdicts and evidence, and optionally up to 3 related articles from other sources covering the same story.

**Use it when:** you need the full picture on a story, want to check specific claims, or need multiple perspectives on the same event.

### `browse_category`

Browse articles within a specific category or tag. Complements `search_news` — use it when you want to explore a topic area rather than search for keywords.

```
→ browse_category(category="technology", sentiment="positive", limit=20)
```

Accepts category names or slugs (e.g., `"artificial-intelligence"` or `"artificial intelligence"` — both work). If the category has no direct matches, it falls back to tag-based matching. Use the `country` parameter to filter by country code.

**Use it when:** exploring what's available in a topic area, filtering a category by sentiment, or following a trending topic from `get_briefing`.

### `list_categories`

Lists all active categories with article counts. Use it to discover what topics are available before calling `browse_category`.

```
→ list_categories(hours=48)
```

**Use it when:** you need to know what's in the news landscape, or before browsing to find valid category names.

### `list_countries`

Lists all countries mentioned in recent articles with article counts. Use it to discover which countries are in the news, then filter `search_news` or `browse_category` by country.

```
→ list_countries(hours=48)
```

**Use it when:** you want to find news about a specific country, or understand the geographic distribution of current coverage.

## Connecting

### Remote (HTTP)

For remote agents or third-party integrations. Requires an API key:

```
POST https://your-instance.example/mcp
Authorization: Bearer <your-api-key>
```

The remote endpoint exposes the same 6 tools with identical schemas. API keys are managed through the news48 admin interface. Both `/mcp` and `/mcp/` paths work — the server handles both without redirects, which is critical for browser-based MCP clients.

> **Note for browser-based clients (MCP Inspector, Claude, etc.):** The endpoint handles CORS preflight (`OPTIONS`) requests directly and returns `Access-Control-Allow-Origin: *` on all responses, including auth errors. This ensures browser-based tools can read error details instead of getting generic "Failed to fetch" errors.

#### Troubleshooting Remote Connections

| Symptom | Cause | Fix |
|---------|-------|-----|
| `Failed to fetch (check CORS?)` | Browser blocked by CORS preflight | Verify the server is running and reachable; check that no reverse proxy strips CORS headers |
| `401 Unauthorized` | Missing or invalid API key | Generate a key with `news48 mcp create-key` and pass it in the `Authorization` header |
| `Connection refused` | Server not running or wrong port | Check `docker compose ps web` and verify the port mapping |
| `307 Temporary Redirect` | Old server version with trailing-slash redirect | Update to latest — the endpoint now handles both `/mcp` and `/mcp/` directly |

#### Deploying Behind a Reverse Proxy (nginx)

If your MCP endpoint is behind an nginx reverse proxy, you must configure it to preserve streaming responses and pass through CORS headers. The backend applies CORS headers automatically, but nginx must not strip or buffer them.

**nginx location block:**

```nginx
location /mcp/ {
    proxy_pass http://backend:8000/mcp/;
    
    # --- Streaming support (critical for Streamable HTTP) ---
    proxy_buffering off;           # Disable response buffering — required for streaming
    proxy_http_version 1.1;        # HTTP/1.1 for keep-alive
    proxy_set_header Connection ""; # Allow connection reuse
    
    # --- Header forwarding ---
    proxy_set_header Authorization $http_authorization;  # Must forward Bearer token
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Forwarded-Proto $scheme;
    
    # --- CORS headers (pass through or set at proxy) ---
    add_header Access-Control-Allow-Origin * always;
    add_header Access-Control-Allow-Methods "GET, POST, DELETE, OPTIONS" always;
    add_header Access-Control-Allow-Headers "*" always;
}
```

**Key requirements:**
1. **`proxy_buffering off`** — Without this, nginx buffers the entire response, breaking streaming and causing hangs
2. **`proxy_set_header Authorization $http_authorization`** — Must forward Bearer tokens to the backend
3. **`add_header ... always`** — Ensures CORS headers are returned even on error responses
4. **`proxy_http_version 1.1`** and **`proxy_set_header Connection ""`** — Enable HTTP/1.1 connection reuse

**Test the configuration:**

```bash
# Verify CORS preflight returns 200 with proper headers
curl -i -X OPTIONS http://your-domain/mcp/ \
  -H "Origin: http://localhost:3000"

# Test with a Bearer token
curl -i -X POST http://your-domain/mcp/ \
  -H "Authorization: Bearer YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "method": "list_tools", "id": 1}'
```

For complete deployment guidance, see [Reverse Proxy Configuration (nginx)](./deployment.md#reverse-proxy-configuration-nginx) in the deployment guide.

## Response Format

All tools return JSON. Every article in every response uses the same compact shape:

```json
{
  "id": 123,
  "title": "Article title",
  "summary": "LLM-rewritten summary",
  "url": "https://source.com/article",
  "source_name": "Source Name",
  "published_at": "2026-04-25T10:00:00Z",
  "categories": "technology, ai",
  "sentiment": "neutral",
  "fact_check_status": "verified"
}
```

Full article responses (via `get_article`) include additional fields: `content`, `author`, `tags`, `countries`, `language`, `fact_check_result`, `fact_checked_at`.

Fact-check statuses: `verified`, `disputed`, `mixed`, `unverifiable`, or `null` (not yet checked).

## Common Patterns

**Briefing → Drill-down:**

1. `get_briefing()` — get the overview
2. Pick an interesting article from `top_stories`
3. `get_article(article_id=N)` — deep dive with claims

**Search → Explore:**

1. `search_news(query="election")` — find relevant articles
2. `get_article(article_id=N, include_related=true)` — read one + see related

**Category browsing:**

1. `list_categories()` — see what's available
2. `browse_category(category="politics")` — explore a topic

**Fact-checking flow:**

1. `search_news(query="specific claim")` — find source articles
2. `get_article(article_id=N)` — read claims and verdicts
3. `get_article(article_id=RELATED_ID)` — cross-reference with related coverage

**Country-focused search:**

1. `list_countries()` — see which countries are mentioned
2. `search_news(query="election", country="us")` — find US election news
3. `browse_category(category="politics", country="gb")` — UK politics
