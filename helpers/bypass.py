"""Bypass solution and content fetching utilities."""

import json
import re
import time
from pathlib import Path

import httpx

import config
from models import ByparrSolution

# Solution file cache
_CACHE_TTL = 3600  # 1 hour


def _get_cache_path(domain: str) -> Path:
    """Get the cache file path for a domain."""
    (config.CACHE_DIR / "byparr").mkdir(parents=True, exist_ok=True)
    return config.CACHE_DIR / "byparr" / f"{domain}.json"


def _load_cached_solution(domain: str) -> ByparrSolution | None:
    """Load a cached solution if it exists and is not stale."""
    cache_path = _get_cache_path(domain)
    if not cache_path.exists():
        return None
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        if time.time() - data.get("timestamp", 0) < _CACHE_TTL:
            return ByparrSolution(
                cookies=data["cookies"],
                headers=data["headers"],
            )
    except (json.JSONDecodeError, OSError, KeyError):
        pass
    return None


def _cache_solution(domain: str, solution: ByparrSolution) -> None:
    """Cache a bypass solution for a domain."""
    cache_path = _get_cache_path(domain)
    data = {
        "cookies": solution.cookies,
        "headers": solution.headers,
        "timestamp": time.time(),
    }
    cache_path.write_text(json.dumps(data), encoding="utf-8")


async def get_byparr_solution(target_url: str, bypass_api_url: str) -> ByparrSolution:
    """Fetch a bypass solution using byparr

    Sends a POST request to the bypass API to get cookies and headers
    for bypassing anti-bot protection on the target URL.

    Args:
        target_url: The URL to fetch (the protected page).
        bypass_api_url: The URL of the bypass API service.

    Returns:
        A ByparrSolution containing cookies and headers for the request.

    Raises:
        httpx.HTTPError: If the request fails.
        ValueError: If the API response is invalid or indicates failure.
    """
    from helpers.url import get_base_url

    domain = get_base_url(target_url)

    # Check cache first
    cached = _load_cached_solution(domain)
    if cached is not None:
        return cached

    timeout = httpx.Timeout(120.0, connect=30.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            bypass_api_url,
            json={
                "cmd": "request.get",
                "url": target_url,
                "maxTimeout": 60000,
            },
        )
        response.raise_for_status()
        data = response.json()

        if data.get("status") != "ok":
            error_msg = data.get("message", "Unknown error")
            raise ValueError(f"Bypass API error: {error_msg}")

        solution_data = data.get("solution")
        if not solution_data:
            raise ValueError("Response missing 'solution' key")

        # Extract and sanitize cookies as (name, value) tuples for httpx
        # Remove newlines and other invalid characters from cookie values
        cookies: list[tuple[str, str]] = []
        for cookie in solution_data.get("cookies", []):
            name = cookie.get("name", "")
            value = cookie.get("value", "")
            # Sanitize both name and value
            if name and value:
                sanitized_name = str(name).replace("\n", " ").replace("\r", "").strip()
                sanitized_value = (
                    str(value).replace("\n", " ").replace("\r", "").strip()
                )
                if sanitized_name and sanitized_value:
                    cookies.append((sanitized_name, sanitized_value))

        # Extract and sanitize headers from the solution
        # Remove newlines and other invalid characters from header values
        # Filter out response-only headers like 'set-cookie'
        raw_headers = solution_data.get("headers", {})
        headers = {}
        for key, value in raw_headers.items():
            # Skip response-only headers that shouldn't be sent in requests
            key_lower = key.lower()
            if key_lower in (
                "set-cookie",
                "content-length",
                "transfer-encoding",
            ):
                continue
            # Convert to string and strip newlines and surrounding whitespace
            if value is not None:
                sanitized_value = (
                    str(value).replace("\n", " ").replace("\r", "").strip()
                )
                if sanitized_value:  # Only add non-empty values
                    headers[key] = sanitized_value

        # Ensure we have a user-agent (required for most websites)
        if "user-agent" not in headers:
            headers["user-agent"] = (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) "
                "Gecko/20100101 Firefox/125.0"
            )

        solution = ByparrSolution(
            cookies=cookies,
            headers=headers,
        )

        # Cache the result
        _cache_solution(domain, solution)
        return solution


async def fetch_url_content(url: str, solution: ByparrSolution) -> str:
    """Fetch the content of a URL using the bypass solution.

    Args:
        url: The URL to fetch.
        solution: The bypass solution containing headers and cookies.

    Returns:
        The raw HTML content of the page.

    Raises:
        httpx.HTTPError: If the request fails.
    """
    timeout = httpx.Timeout(120.0, connect=30.0)

    # Merge solution headers with additional browser-like headers
    headers = dict(solution.headers) if solution.headers else {}

    # Add standard browser headers if not already present
    headers.setdefault(
        "Accept",
        "text/html,application/xhtml+xml,application/xml;q=0.9," "image/webp,*/*;q=0.8",
    )
    headers.setdefault("Accept-Language", "en-US,en;q=0.9")
    headers.setdefault("Accept-Encoding", "gzip, deflate")
    headers.setdefault("DNT", "1")
    headers.setdefault("Connection", "keep-alive")
    headers.setdefault("Upgrade-Insecure-Requests", "1")
    headers.setdefault("Cache-Control", "no-cache")

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        response = await client.get(url=url, cookies=solution.cookies, headers=headers)
        response.raise_for_status()
        return response.content.decode()


def strip_html_noise(html_content: str) -> str:
    """Remove unnecessary tags and attributes from HTML to reduce token count.

    Strips content that is irrelevant for article text extraction:
    - Entire <head> section (title is stored as a separate DB field)
    - <script>, <style>, <noscript>, <iframe>, <svg> tags with content
    - <link>, <meta>, <img>, <input>, <button> self-closing/void tags
    - Custom elements (e.g. <ad-slot>)
    - HTML comments
    - Presentational attributes: class, id, style, data-*, on*, target
    - Empty tags (multiple passes for nested empties)
    - Excessive blank lines
    - Extracts only <body> content (discards <html>/<body> wrappers)

    Args:
        html_content: Raw HTML string to clean.

    Returns:
        Cleaned HTML with noise removed, suitable for LLM processing.
    """
    _sub = re.sub
    I = re.IGNORECASE  # noqa: E741
    D = re.DOTALL
    ID = I | D

    # --- Phase 0: Remove DOCTYPE and unescape HTML entities ---

    # Remove <!doctype html> (case insensitive)
    html_content = _sub(r"<!doctype\s+html[^>]*>", "", html_content, flags=I)

    # Unescape HTML entities.  Named entities are replaced first so that
    # explicit entries like &quot; and &#39; are handled before the generic
    # numeric-entity regexes run (which would otherwise shadow them).
    #
    # Order:
    #   1. Named entities  (&amp; &lt; &gt; &quot; &#39;)
    #   2. Hex numeric     (&#xHH;)
    #   3. Decimal numeric (&#DD;)
    #   4. &nbsp; removal

    # 1. Named / well-known entities.
    # &amp; is decoded in a loop to handle double-encoded entities
    # (e.g. &amp;amp; -> &amp; -> &).
    while "&amp;" in html_content:
        html_content = html_content.replace("&amp;", "&")
    html_content = html_content.replace("&lt;", "<")
    html_content = html_content.replace("&gt;", ">")
    html_content = html_content.replace("&quot;", '"')
    html_content = html_content.replace("&#39;", "'")

    # 2–3. Remaining numeric entities (hex then decimal)
    def _hex_entity_replace(m: re.Match[str]) -> str:
        try:
            return chr(int(m.group(1), 16))
        except (ValueError, OverflowError):
            return m.group(0)

    def _decimal_entity_replace(m: re.Match[str]) -> str:
        try:
            return chr(int(m.group(1)))
        except (ValueError, OverflowError):
            return m.group(0)

    html_content = _sub(r"&#x([0-9a-fA-F]+);", _hex_entity_replace, html_content)
    html_content = _sub(r"&#(\d+);", _decimal_entity_replace, html_content)

    # 4. Remove &nbsp; entirely (not replace with space) to save tokens.
    # The trailing semicolon is optional to handle malformed HTML (&nbsp).
    html_content = _sub(r"&nbsp;?", "", html_content)

    # Strip literal backslash-space sequences ("\ ") that some sites inject
    # via CSS content properties or JS-generated markup.
    html_content = _sub(r"\\ ", "", html_content)

    # --- Phase 1: Remove entire tag blocks with content ---

    # Strip <head> entirely (title is stored as a separate DB field)
    html_content = _sub(r"<head[^>]*>.*?</head>", "", html_content, flags=ID)

    # Tags with content to remove entirely
    for tag in (
        "script",
        "style",
        "noscript",
        "iframe",
        "svg",
        "form",
        "video",
    ):
        html_content = _sub(
            rf"<{tag}[^>]*>.*?</{tag}>",
            "",
            html_content,
            flags=ID,
        )

    # Void / self-closing tags to remove
    html_content = _sub(
        r"<(?:link|meta|img|input|button|source|br|hr)[^>]*?/?>",
        "",
        html_content,
        flags=I,
    )

    # Custom elements like <ad-slot ...>...</ad-slot> and self-closing
    # Matches elements with hyphens (web components), e.g. <my-element>,
    # <x-ab2>, <my-custom-element>
    html_content = _sub(
        r"<([a-z][a-z0-9]*(?:-[a-z0-9]+)+)[^>]*/?>(?:.*?</\1>)?",
        "",
        html_content,
        flags=ID,
    )

    # HTML comments
    html_content = _sub(r"<!--.*?-->", "", html_content, flags=D)

    # --- Phase 2: Strip noisy attributes ---

    # Remove on* event handlers (handles both double and single quoted values)
    html_content = _sub(
        r'\s+on\w+="[^"]*"',
        "",
        html_content,
        flags=I,
    )
    html_content = _sub(
        r"\s+on\w+='[^']*'",
        "",
        html_content,
        flags=I,
    )

    # Remove data-* attributes (supports hyphenated names like
    # data-ad-marker-group, data-track-module, etc.)
    # Handles both quoted values and valueless bare attributes.
    html_content = _sub(
        r'\s+data-[\w-]+=["\'][^"\']*["\']',
        "",
        html_content,
    )
    html_content = _sub(
        r"\s+data-[\w-]+(?=\s|>|/>)",
        "",
        html_content,
    )

    # Remove class, id, style, target, role attributes.
    # Handles quoted ("..." / '...') and unquoted (bare-word) values.
    for attr in ("class", "id", "style", "target", "role"):
        html_content = _sub(
            rf"""\s+{attr}=(?:["\'][^"\']*["\']|\S+)""",
            "",
            html_content,
            flags=I,
        )

    # --- Phase 3: Clean up empty tags and whitespace ---

    # Remove empty tags (multiple passes for nested empties).
    # Uses a callback so the open/close tag comparison is case-insensitive
    # (re backreferences like \1 are always case-sensitive, even with re.I).
    def _remove_empty_tag(m: re.Match[str]) -> str:
        if m.group(1).lower() == m.group(2).lower():
            return ""
        return m.group(0)

    _empty_tag_re = re.compile(r"<(\w+)[^>]*>\s*</(\w+)>", I)
    for _ in range(3):
        html_content = _empty_tag_re.sub(_remove_empty_tag, html_content)

    # Collapse runs of blank lines into a single blank line
    html_content = _sub(r"\n\s*\n(\s*\n)+", "\n\n", html_content)

    # Strip leading/trailing whitespace on each line
    html_content = "\n".join(line.strip() for line in html_content.splitlines())

    # Final collapse of any remaining multiple blank lines
    html_content = _sub(r"\n{3,}", "\n\n", html_content)

    # --- Final Phase: Extract body content only ---
    body_match = re.search(r"<body[^>]*>(.*)</body>", html_content, flags=ID)
    if body_match:
        html_content = body_match.group(1)

    return html_content.strip()
