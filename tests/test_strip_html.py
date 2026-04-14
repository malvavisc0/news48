"""Tests for strip_html_noise(), extract_og_image() ordering,
and _strip_html_tags()."""

import sqlite3
from pathlib import Path

import pytest

from helpers.bypass import strip_html_noise
from helpers.url import extract_og_image

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
    def db_path(self, tmp_path: Path) -> Path:
        """Create a minimal test database with an articles table."""
        db_file = tmp_path / "test.db"
        conn = sqlite3.connect(db_file)
        conn.execute("""
            CREATE TABLE articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fetch_id INTEGER,
                feed_id INTEGER,
                url TEXT UNIQUE,
                title TEXT,
                summary TEXT,
                content TEXT,
                author TEXT,
                published_at TEXT,
                sentiment TEXT,
                categories TEXT,
                tags TEXT,
                countries TEXT,
                image_url TEXT,
                language TEXT,
                parsed_at TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                source_name TEXT,
                processing_claim_owner TEXT,
                processing_claim_expires TEXT,
                download_error TEXT,
                fact_check_status TEXT,
                fact_check_result TEXT,
                fact_checked_at TEXT
            )
        """)
        conn.execute(
            "INSERT INTO articles "
            "(fetch_id, feed_id, url, title, summary, content) "
            "VALUES (1, 1, 'https://example.com/test', "
            "'Test', 'Test summary', 'Test content')"
        )
        conn.commit()
        conn.close()
        return db_file

    def test_strips_html_from_summary(self, db_path: Path) -> None:
        from database.articles import update_article

        update_article(db_path, 1, content="clean", summary="<b>Bold</b> summary")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT summary FROM articles WHERE id = 1").fetchone()
        conn.close()
        assert row["summary"] == "Bold summary"

    def test_strips_html_from_title(self, db_path: Path) -> None:
        from database.articles import update_article

        update_article(db_path, 1, content="clean", title="<i>Italic</i> Title")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT title FROM articles WHERE id = 1").fetchone()
        conn.close()
        assert row["title"] == "Italic Title"

    def test_strips_html_from_content(self, db_path: Path) -> None:
        from database.articles import update_article

        update_article(
            db_path,
            1,
            content="<p>Paragraph</p> with <a href='#'>link</a>",
        )
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT content FROM articles WHERE id = 1").fetchone()
        conn.close()
        assert row["content"] == "Paragraph with link"

    def test_none_values_unchanged(self, db_path: Path) -> None:
        from database.articles import update_article

        # Should not raise when summary/title are None
        update_article(db_path, 1, content="clean", summary=None, title=None)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT content FROM articles WHERE id = 1").fetchone()
        conn.close()
        assert row["content"] == "clean"
