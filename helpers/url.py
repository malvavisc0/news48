"""URL utilities."""


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
