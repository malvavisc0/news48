"""Helper functions for feed fetching and content utilities.

This module provides utilities organized into submodules:
- feed: Feed fetching and date utilities
- bypass: Bypass solution and content fetching
- url: URL utilities
- seo: SEO and social sharing metadata helpers
- security: URL validation, SQL escape helpers
- text: Shared text processing utilities

Submodules are NOT eagerly imported here to avoid circular dependencies
(e.g. feed → database → articles → helpers.security → this __init__).
Import directly from the submodule instead:

    from news48.core.helpers.feed import load_urls
    from news48.core.helpers.bypass import fetch_url_content
"""
