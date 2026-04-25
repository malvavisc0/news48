"""Tests for strip_html_noise(), extract_og_image() ordering,
and _strip_html_tags()."""

import pytest

from news48.core.helpers.bypass import strip_html_noise
from news48.core.helpers.url import extract_og_image

# ---------------------------------------------------------------------------
# strip_html_noise() — body extraction
# ---------------------------------------------------------------------------


class TestStripHtmlNoiseBodyExtraction:
    """Verify that strip_html_noise() returns only <body> content."""

    def test_extracts_body_content(self) -> None:
        html = (
            "<html><head><title>Test</title></head>"
            "<body><p>Hello world</p></body></html>"
        )
        result = strip_html_noise(html)
        assert "<head>" not in result
        assert "<html" not in result
        assert "<body" not in result
        assert "</body>" not in result
        assert "Hello world" in result

    def test_no_body_tag_returns_everything(self) -> None:
        """No <body> tag — function should still return content."""
        html = "<p>No body tag here</p>"
        result = strip_html_noise(html)
        assert "No body tag here" in result

    def test_body_with_attributes(self) -> None:
        html = '<html><body class="main"><p>Content</p></body></html>'
        result = strip_html_noise(html)
        assert "Content" in result
        assert "<body" not in result

    def test_head_removed_entirely(self) -> None:
        html = (
            "<html><head><meta charset='utf-8'>"
            "<link rel='stylesheet' href='style.css'>"
            "<title>My Title</title></head>"
            "<body><p>Article text</p></body></html>"
        )
        result = strip_html_noise(html)
        assert "<head>" not in result
        assert "My Title" not in result
        assert "Article text" in result

    def test_script_tags_inside_body_removed(self) -> None:
        html = (
            "<html><body>"
            "<p>Keep this</p>"
            "<script>var x = 1;</script>"
            "<p>Also keep this</p>"
            "</body></html>"
        )
        result = strip_html_noise(html)
        assert "var x" not in result
        assert "Keep this" in result
        assert "Also keep this" in result

    def test_style_tags_inside_body_removed(self) -> None:
        html = (
            "<html><body>"
            "<style>.foo { color: red; }</style>"
            "<p>Content</p>"
            "</body></html>"
        )
        result = strip_html_noise(html)
        assert "color: red" not in result
        assert "Content" in result


# ---------------------------------------------------------------------------
# extract_og_image() — must work on raw HTML, not stripped HTML
# ---------------------------------------------------------------------------


class TestExtractOgImageOrdering:
    """Verify extract_og_image() works on raw HTML (before stripping)."""

    def test_og_image_found_in_raw_html(self) -> None:
        raw_html = (
            "<html><head>"
            '<meta property="og:image" '
            'content="https://example.com/image.jpg">'
            "</head><body><p>Article</p></body></html>"
        )
        # On raw HTML, og:image should be found
        assert extract_og_image(raw_html) == "https://example.com/image.jpg"

    def test_og_image_not_found_in_stripped_html(self) -> None:
        """After strip_html_noise(), og:image meta tags are removed."""
        raw_html = (
            "<html><head>"
            '<meta property="og:image" '
            'content="https://example.com/image.jpg">'
            "</head><body><p>Article</p></body></html>"
        )
        stripped = strip_html_noise(raw_html)
        # After stripping, og:image should NOT be found
        assert extract_og_image(stripped) is None

    def test_twitter_image_found_in_raw_html(self) -> None:
        raw_html = (
            "<html><head>"
            '<meta name="twitter:image" '
            'content="https://example.com/tw.jpg">'
            "</head><body><p>Article</p></body></html>"
        )
        assert extract_og_image(raw_html) == "https://example.com/tw.jpg"

    def test_og_image_none_when_no_meta(self) -> None:
        html = "<html><body><p>No meta tags</p></body></html>"
        assert extract_og_image(html) is None


# ---------------------------------------------------------------------------
# _strip_html_tags() in database/articles.py
# ---------------------------------------------------------------------------


class TestStripHtmlTagsInUpdateArticle:
    """Verify update_article() strips HTML from summary, title, content."""

    @pytest.fixture()
    def article_id(self, db_session) -> int:
        """Create a test article using the SQLAlchemy session fixture."""
        from news48.core.database.models import Article, Feed, Fetch

        feed = Feed(
            url="https://example.com/feed.xml",
            created_at="2024-01-01T00:00:00+00:00",
        )
        db_session.add(feed)
        db_session.flush()

        fetch = Fetch(
            started_at="2024-01-01T00:00:00+00:00",
            status="running",
        )
        db_session.add(fetch)
        db_session.flush()

        article = Article(
            fetch_id=fetch.id,
            feed_id=feed.id,
            url="https://example.com/test",
            title="Test",
            summary="Test summary",
            content="Test content",
            created_at="2024-01-01T00:00:00+00:00",
        )
        db_session.add(article)
        db_session.flush()
        return article.id

    def test_strips_html_from_summary(self, article_id: int, db_session) -> None:
        # Clear existing summary first so SD-1 allows the update
        # (SD-1: only update metadata if current value is NULL/empty)
        from news48.core.database.articles import update_article
        from news48.core.database.models import Article

        art = db_session.get(Article, article_id)
        if art:
            art.summary = None
            db_session.commit()

        update_article(article_id, content="clean", summary="<b>Bold</b> summary")
        from news48.core.database.articles import get_article_by_id

        article = get_article_by_id(article_id)
        assert article["summary"] == "Bold summary"

    def test_strips_html_from_title(self, article_id: int) -> None:
        from news48.core.database.articles import update_article

        update_article(article_id, content="clean", title="<i>Italic</i> Title")
        from news48.core.database.articles import get_article_by_id

        article = get_article_by_id(article_id)
        assert article["title"] == "Italic Title"

    def test_strips_html_from_content(self, article_id: int) -> None:
        from news48.core.database.articles import update_article

        update_article(
            article_id,
            content="<p>Paragraph</p> with <a href='#'>link</a>",
        )
        from news48.core.database.articles import get_article_by_id

        article = get_article_by_id(article_id)
        assert article["content"] == "Paragraph with link"

    def test_none_values_unchanged(self, article_id: int) -> None:
        from news48.core.database.articles import update_article

        # Should not raise when summary/title are None
        update_article(article_id, content="clean", summary=None, title=None)
        from news48.core.database.articles import get_article_by_id

        article = get_article_by_id(article_id)
        assert article["content"] == "clean"
