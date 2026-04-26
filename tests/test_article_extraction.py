"""Tests for readability-based article body extraction.

These tests exercise ``extract_article_body()`` from
``news48.core.helpers.bypass`` with a focus on:
  - Navigation-heavy HTML being cleaned up
  - Simple article content being preserved
  - The ``ARTICLE_EXTRACTION=none`` config skip
  - Fallback behaviour when trafilatura raises errors
"""

from unittest.mock import patch

from news48.core.helpers.bypass import extract_article_body

# ---------------------------------------------------------------------------
# Helper fixtures
# ---------------------------------------------------------------------------

NAV_HEAVY_HTML = """
<html><head><title>Test</title></head><body>
<nav>
  <a href="/">Home</a>
  <a href="/about">About</a>
  <a href="/contact">Contact</a>
  <a href="/privacy">Privacy Policy</a>
</nav>
<header>
  <h1>Site Name</h1>
  <ul>
    <li>Menu item 1</li>
    <li>Menu item 2</li>
    <li>Menu item 3</li>
  </ul>
</header>
<article>
  <h2>Breaking News: Important Event Happens</h2>
  <p>This is the actual article content with meaningful text that should
  be preserved by the extraction process. It contains enough detail to
  be identified as the primary content of the page.</p>
  <p>A second paragraph adds more substance and helps trafilatura
  distinguish the article body from the surrounding chrome.</p>
</article>
<footer>
  <p>Copyright 2026</p>
  <ul>
    <li><a href="/terms">Terms of Service</a></li>
    <li><a href="/privacy">Privacy</a></li>
  </ul>
</footer>
</body></html>
"""

SIMPLE_ARTICLE_HTML = "<p>Simple article with one paragraph of meaningful content.</p>"

COOKIE_BANNER_HTML = """
<html><body>
<div id="cookie-banner">
  <p>We use cookies to improve your experience. Accept all cookies?</p>
  <button>Accept</button>
  <button>Reject</button>
</div>
<article>
  <h1>Real Article Title</h1>
  <p>The actual article text is here and contains enough words for
  trafilatura to identify it as the main content block.</p>
  <p>Additional paragraph with more real content for extraction.</p>
</article>
</body></html>
"""


# ---------------------------------------------------------------------------
# Core extraction tests
# ---------------------------------------------------------------------------


class TestExtractArticleBody:
    """Unit tests for extract_article_body()."""

    def test_removes_navigation_elements(self):
        """Navigation-heavy HTML should have the article extracted."""
        result = extract_article_body(NAV_HEAVY_HTML)
        # The article content must survive extraction
        assert (
            "actual article content" in result.lower()
            or "actual article content" in result
        )
        # The navigation links should not dominate the result
        assert "/privacy" not in result

    def test_preserves_simple_article(self):
        """Clean article HTML should be preserved."""
        result = extract_article_body(SIMPLE_ARTICLE_HTML)
        assert "Simple article" in result

    def test_removes_cookie_banner(self):
        """Cookie banners should be discarded, article kept."""
        result = extract_article_body(COOKIE_BANNER_HTML)
        assert "cookie" not in result.lower()
        assert "Real Article Title" in result or "actual article text" in result.lower()

    def test_returns_nonempty_string(self):
        """Extraction must never return an empty string for valid HTML."""
        result = extract_article_body(NAV_HEAVY_HTML)
        assert len(result) > 0

    def test_plain_text_passthrough(self):
        """Plain text input should be preserved via fallback."""
        text = "This is just plain text with no HTML tags at all."
        result = extract_article_body(text)
        # trafilatura may return None for non-HTML input, which triggers
        # the fallback that returns original content
        assert "plain text" in result


# ---------------------------------------------------------------------------
# Config-gated tests
# ---------------------------------------------------------------------------


class TestExtractionConfig:
    """Tests for the ARTICLE_EXTRACTION config toggle."""

    def test_skip_when_mode_none(self):
        """When mode is 'none', extraction should be a no-op."""
        with patch.object(
            __import__("news48.core.config", fromlist=["Extraction"]).Extraction,
            "mode",
            "none",
        ):
            result = extract_article_body(NAV_HEAVY_HTML)
            # Should return the input unchanged
            assert result == NAV_HEAVY_HTML

    def test_runs_when_mode_trafilatura(self):
        """When mode is 'trafilatura', extraction should run."""
        with patch.object(
            __import__("news48.core.config", fromlist=["Extraction"]).Extraction,
            "mode",
            "trafilatura",
        ):
            result = extract_article_body(NAV_HEAVY_HTML)
            # The extraction should modify the content
            assert isinstance(result, str)
            assert len(result) > 0


# ---------------------------------------------------------------------------
# Fallback tests
# ---------------------------------------------------------------------------


class TestFallbackBehaviour:
    """Tests for graceful degradation when extraction fails."""

    def test_fallback_on_import_error(self):
        """If trafilatura can't be imported, original HTML is returned."""
        with patch.dict("sys.modules", {"trafilatura": None}):
            result = extract_article_body(NAV_HEAVY_HTML)
            assert result == NAV_HEAVY_HTML

    def test_fallback_on_exception(self):
        """If trafilatura.extract raises, original HTML is returned."""
        import trafilatura

        orig = trafilatura.extract
        try:
            trafilatura.extract = lambda *a, **kw: (_ for _ in ()).throw(
                RuntimeError("simulated failure")
            )
            result = extract_article_body(NAV_HEAVY_HTML)
            assert result == NAV_HEAVY_HTML
        finally:
            trafilatura.extract = orig

    def test_fallback_when_extraction_returns_none(self):
        """If trafilatura returns None, original HTML is returned."""
        import trafilatura

        orig = trafilatura.extract
        try:
            trafilatura.extract = lambda *a, **kw: None
            result = extract_article_body(NAV_HEAVY_HTML)
            assert result == NAV_HEAVY_HTML
        finally:
            trafilatura.extract = orig


# ---------------------------------------------------------------------------
# Integration-style tests (calling the function with realistic HTML)
# ---------------------------------------------------------------------------


class TestRealisticExtraction:
    """Tests with realistic HTML resembling actual news sites."""

    REALISTIC_HTML = """
    <!DOCTYPE html>
    <html lang="en">
    <head><title>Breaking: Major Event - News Site</title></head>
    <body>
    <nav class="main-nav">
        <ul>
            <li><a href="/">Home</a></li>
            <li><a href="/world">World</a></li>
            <li><a href="/politics">Politics</a></li>
            <li><a href="/tech">Technology</a></li>
            <li><a href="/sports">Sports</a></li>
        </ul>
    </nav>
    <div class="cookie-consent">
        <p>This site uses cookies. By continuing to browse, you agree
        to our use of cookies.</p>
        <button>OK</button>
    </div>
    <main>
        <article>
            <h1>Scientists Discover New Species in Deep Ocean</h1>
            <p class="byline">By Jane Smith | Published April 26, 2026</p>
            <p>A team of marine biologists has discovered a previously
            unknown species of bioluminescent fish living at depths
            exceeding 3,000 meters in the Pacific Ocean. The discovery
            was made during a six-week expedition aboard the research
            vessel Oceanus.</p>
            <p>The fish, tentatively named Bathylagus luminaris, emits
            a distinctive blue-green glow that researchers believe is
            used for communication in the pitch-dark deep sea
            environment.</p>
            <p>Dr. Maria Chen, lead researcher on the expedition,
            described the find as remarkable. In thirty years of deep-sea
            research, I have never encountered anything quite like this
            creature, she said at a press conference.</p>
        </article>
    </main>
    <aside class="sidebar">
        <h3>Trending</h3>
        <ul>
            <li><a href="/trending/1">Other news story</a></li>
            <li><a href="/trending/2">Another story</a></li>
        </ul>
    </aside>
    <footer>
        <p>&copy; 2026 News Site. All rights reserved.</p>
        <ul>
            <li><a href="/about">About Us</a></li>
            <li><a href="/contact">Contact</a></li>
            <li><a href="/privacy">Privacy Policy</a></li>
        </ul>
    </footer>
    </body>
    </html>
    """

    def test_realistic_article_content_preserved(self):
        """Real-world HTML should yield the article body."""
        result = extract_article_body(self.REALISTIC_HTML)
        assert "Scientists Discover" in result
        assert "bioluminescent fish" in result
        assert "Bathylagus luminaris" in result

    def test_realistic_navigation_removed(self):
        """Navigation chrome should be stripped from realistic HTML."""
        result = extract_article_body(self.REALISTIC_HTML)
        # Navigation and footer links should not be present
        assert "/politics" not in result
        assert "Privacy Policy" not in result

    def test_realistic_cookie_banner_removed(self):
        """Cookie consent banner should not appear in output."""
        result = extract_article_body(self.REALISTIC_HTML)
        assert "cookie" not in result.lower()
