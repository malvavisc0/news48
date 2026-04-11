from os import getenv
from typing import Any, Dict, Literal, TypedDict
from urllib.parse import urlencode

import httpx

from agents.tools._helpers import _clean_text, _safe_json

SEARXNG_URL = getenv("SEARXNG_URL", "").rstrip("/")
_REQUEST_TIMEOUT_SECONDS = 10.0

Categories = Literal[
    "general",
    "files",
    "news",
    "videos",
    "images",
]
TimeRange = Literal["", "day", "week", "month", "year"]


class FieldSpec(TypedDict):
    name: str
    required: bool
    default: Any


class SearchPageStats(TypedDict):
    requested: int
    succeeded: int
    failed: int


# Field mappings per category.
_CATEGORY_FIELD_MAP: Dict[str, list[FieldSpec]] = {
    "general": [
        {"name": "url", "required": True, "default": None},
        {"name": "title", "required": True, "default": None},
        {"name": "content", "required": True, "default": None},
    ],
    "news": [
        {"name": "url", "required": True, "default": None},
        {"name": "title", "required": True, "default": None},
        {"name": "content", "required": True, "default": None},
        {"name": "source", "required": False, "default": ""},
        {"name": "thumbnail", "required": False, "default": ""},
        {"name": "pubdate", "required": False, "default": ""},
    ],
    "images": [
        {"name": "url", "required": True, "default": None},
        {"name": "title", "required": True, "default": None},
        {"name": "img_src", "required": True, "default": None},
        {"name": "thumbnail_src", "required": False, "default": ""},
    ],
    "videos": [
        {"name": "url", "required": True, "default": None},
        {"name": "title", "required": True, "default": None},
        {"name": "content", "required": True, "default": None},
        {"name": "iframe_src", "required": False, "default": ""},
        {"name": "thumbnail", "required": False, "default": ""},
        {"name": "engine", "required": False, "default": ""},
    ],
    "files": [
        {"name": "url", "required": True, "default": None},
        {"name": "title", "required": True, "default": None},
        {"name": "content", "required": True, "default": None},
        {"name": "filename", "required": True, "default": None},
        {"name": "size", "required": False, "default": ""},
        {"name": "mimetype", "required": False, "default": ""},
    ],
}


def perform_web_search(
    reason: str,
    query: str,
    category: Categories = "general",
    time_range: TimeRange = "",
    pages: int = 3,
) -> str:
    """Search the web via SearXNG and return normalized results.

    ## When to Use
    Use this tool when you need current web search results for research,
    fact-checking, or finding recent information. For fetching specific
    URLs directly, use `fetch_webpage_content` instead.

    ## Why to Use
    - Get fresh, up-to-date information from the web
    - Research topics with multiple source results
    - Find news articles, images, videos, or files
    - Filter results by time range (day/week/month/year)
    - Privacy-respecting search (SearXNG aggregates multiple engines)

    ## Parameters
    - `reason` (str): Why you need these search results
    - `query` (str): Search query text
    - `category` (str): Result type - general, news, images, videos, files
    - `time_range` (str): Freshness filter - day, week, month, year, or ""
    - `pages` (int): Number of result pages to fetch (default: 3)

    ## Returns
    JSON with:
    - `result.count`: Number of results returned
    - `result.findings`: Array of normalized results by category
    - `error`: Empty on success, or partial failure message

    ## Note
    Requires SEARXNG_URL environment variable to be configured.
    """
    if not SEARXNG_URL:
        raise ValueError("SEARXNG_URL environment variable is not set")
    if not query:
        raise ValueError("query cannot be empty")
    if pages < 1:
        raise ValueError("pages must be a positive integer")

    results: list[dict[str, Any]] = []
    page_errors: list[dict[str, Any]] = []
    dropped_results = 0
    stats: SearchPageStats = {"requested": pages, "succeeded": 0, "failed": 0}
    field_map = _CATEGORY_FIELD_MAP.get(category, _CATEGORY_FIELD_MAP["general"])

    with httpx.Client(timeout=_REQUEST_TIMEOUT_SECONDS) as client:
        for page_number in range(1, pages + 1):
            params = {
                "safesearch": "0",
                "format": "json",
                "time_range": time_range,
                "categories": category,
                "q": query,
                "pageno": page_number,
            }
            page_result, page_error, page_dropped = _fetch_page(
                client=client,
                category=category,
                field_map=field_map,
                params=params,
                page_number=page_number,
            )

            dropped_results += page_dropped
            if page_error:
                stats["failed"] += 1
                page_errors.append(page_error)
                continue

            stats["succeeded"] += 1
            results.extend(page_result)

    error_message = _build_error_message(stats=stats, page_errors=page_errors)

    return _safe_json(
        {
            "result": {
                "count": len(results),
                "findings": results,
                "page_stats": stats,
                "dropped_results": dropped_results,
                "page_errors": page_errors,
            },
            "error": error_message,
        }
    )


def _fetch_page(
    *,
    client: httpx.Client,
    category: str,
    field_map: list[FieldSpec],
    params: dict[str, Any],
    page_number: int,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None, int]:
    """Fetch and normalize a single search results page."""
    url = f"{SEARXNG_URL}/search?{urlencode(params)}"

    try:
        response = client.get(url)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        return [], _page_error(page_number, "http_error", str(exc)), 0

    try:
        payload = response.json()
    except ValueError as exc:
        return [], _page_error(page_number, "invalid_json", str(exc)), 0

    raw_results = payload.get("results")
    if not isinstance(raw_results, list):
        return (
            [],
            _page_error(
                page_number,
                "invalid_payload",
                "Missing or invalid 'results' list",
            ),
            0,
        )

    rows: list[dict[str, Any]] = []
    dropped_results = 0
    for raw_result in raw_results:
        if not isinstance(raw_result, dict):
            dropped_results += 1
            continue

        row = _build_row(raw_result, category, field_map)
        if row is None:
            dropped_results += 1
            continue
        rows.append(row)

    return rows, None, dropped_results


def _build_row(
    result: dict[str, Any], category: str, field_map: list[FieldSpec]
) -> dict[str, Any] | None:
    """Build a normalized result row based on category field mapping."""
    row: dict[str, Any] = {}
    for spec in field_map:
        field_name = spec["name"]
        required = spec["required"]
        default = spec["default"]

        value = result.get(field_name, default)
        if required and not value:
            return None

        if field_name in {"title", "content", "filename"} and isinstance(value, str):
            value = _clean_text(value)

        row[field_name] = value

    row["category"] = category
    return row


def _page_error(page_number: int, error_type: str, detail: str) -> dict[str, Any]:
    """Build a structured per-page error payload."""
    return {
        "page": page_number,
        "type": error_type,
        "detail": detail,
    }


def _build_error_message(
    *, stats: SearchPageStats, page_errors: list[dict[str, Any]]
) -> str:
    """Build a top-level error summary for callers."""
    if stats["failed"] == 0:
        return ""
    if stats["succeeded"] == 0:
        return "All search requests failed"
    first_error = page_errors[0]["detail"] if page_errors else "Unknown error"
    return (
        f"Partial search failure: {stats['failed']} of {stats['requested']} "
        f"page requests failed. First error: {first_error}"
    )
