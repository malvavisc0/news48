"""URL utilities."""

import re
import unicodedata


def slugify(title: str | None) -> str:
    """Convert a title into a URL-safe slug.

    Produces lowercase, hyphen-separated tokens with no special characters.
    Example: "US and Iran Blockade Standoff" → "us-and-iran-blockade-standoff"
    """
    if not title:
        return ""
    # Normalize unicode characters
    value = unicodedata.normalize("NFKD", title)
    # Keep only alphanumeric, spaces, and hyphens
    value = re.sub(r"[^\w\s-]", "", value)
    # Collapse whitespace and hyphens into single hyphens
    value = re.sub(r"[\s_]+", "-", value).strip("-")
    return value.lower()


def get_base_url(url: str) -> str:
    """Extract the base URL (scheme + domain) from a full URL.

    Args:
        url: A full URL string (e.g., 'https://example.com/path').

    Returns:
        The base URL with http scheme (e.g., 'example.com').

    Raises:
        ValueError: If the URL is invalid or missing scheme.
    """
    if "://" not in url:
        raise ValueError(f"Invalid URL missing scheme: {url}")
    parts = url.split("://", 1)
    scheme = parts[0]
    if scheme not in ("http", "https"):
        raise ValueError(f"Invalid scheme '{scheme}' in URL: {url}")
    domain = parts[1].split("/")[0]
    return domain


def extract_og_image(html: str) -> str | None:
    """Extract og:image from HTML meta tags.

    Checks in order:
    - <meta property="og:image" content="...">
    - <meta name="twitter:image" content="...">
    - <link rel="image_src" href="...">
    """
    if not html:
        return None

    # og:image
    match = re.search(
        r'<meta\s+[^>]*property=["\']og:image["\'][^>]*' r'content=["\']([^"\']+)["\']',
        html,
        re.IGNORECASE,
    )
    if match:
        return match.group(1)

    # og:image with content before property
    match = re.search(
        r'<meta\s+[^>]*content=["\']([^"\']+)["\'][^>]*' r'property=["\']og:image["\']',
        html,
        re.IGNORECASE,
    )
    if match:
        return match.group(1)

    # twitter:image
    match = re.search(
        r'<meta\s+[^>]*name=["\']twitter:image["\'][^>]*'
        r'content=["\']([^"\']+)["\']',
        html,
        re.IGNORECASE,
    )
    if match:
        return match.group(1)

    # twitter:image with content before name
    match = re.search(
        r'<meta\s+[^>]*content=["\']([^"\']+)["\'][^>]*'
        r'name=["\']twitter:image["\']',
        html,
        re.IGNORECASE,
    )
    if match:
        return match.group(1)

    # link rel="image_src"
    match = re.search(
        r'<link\s+[^>]*rel=["\']image_src["\'][^>]*' r'href=["\']([^"\']+)["\']',
        html,
        re.IGNORECASE,
    )
    if match:
        return match.group(1)

    return None
