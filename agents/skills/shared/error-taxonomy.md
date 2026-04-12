# Skill: Use structured error codes

## Scope
Always active — all agents must use standardized error codes when reporting failures.

## Error Code Format
Error codes follow the pattern `category.detail` — a category prefix, a dot, and a specific detail.

## Categories

| Code | Category | Description |
|------|----------|-------------|
| `net` | Network | Connection timeouts, DNS failures, refused connections |
| `net.timeout` | Network timeout | Request exceeded time limit |
| `net.dns` | DNS failure | Could not resolve hostname |
| `net.refused` | Connection refused | Server rejected connection |
| `net.ssl` | SSL/TLS error | Certificate or handshake failure |
| `src` | Source | Problems with the content source (feed, article page) |
| `src.404` | Not found | Feed URL or article page returned 404 |
| `src.gone` | Permanently gone | Feed has been permanently removed |
| `src.block` | Blocked | Source blocks automated access (Cloudflare, CAPTCHA) |
| `src.empty` | Empty content | Downloaded page has no usable content |
| `src.malformed` | Malformed content | HTML/XML is too broken to parse |
| `parse` | Parse | Problems during article parsing |
| `parse.quality` | Quality gate failure | Parsed content failed quality checks |
| `parse.duplicate_title` | Duplicate title | Summary duplicates the title |
| `parse.out_of_bounds` | Out of bounds | Title, summary, or content length outside limits |
| `parse.invalid_field` | Invalid field | Country code, category, or sentiment normalization failed |
| `parse.fidelity` | Fidelity violation | Invented facts or missing core facts |
| `sys` | System | Infrastructure or tool failures |
| `sys.db` | Database error | SQLite write contention, connection failure |
| `sys.plan` | Plan error | Plan claim failure, stale plan, step transition error |
| `sys.tool` | Tool error | Shell command or file operation failed |

## Rules
1. When reporting a failure (via `news48 articles fail` or plan step failure), always include an error code from this taxonomy.
2. Use the most specific code available. If no specific code fits, use the category prefix alone (e.g., `net` for an unspecified network error).
3. Include the error code before the human-readable message: `net.timeout: Connection timed out after 30s`.
4. Do not invent codes outside this taxonomy. If a new category is needed, add it here first.