"""Tests for strip_html_noise(), extract_og_image() ordering,
strip_html_tags(), strip_markdown(), and _strip_html_tags()."""

import pytest

from news48.core.helpers.bypass import strip_html_noise
from news48.core.helpers.text import strip_html_tags, strip_markdown
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


# ---------------------------------------------------------------------------
# strip_html_tags() — comprehensive unit tests
# ---------------------------------------------------------------------------


class TestStripHtmlTagsNoneAndEmpty:
    """Edge cases: None, empty string, whitespace-only."""

    def test_none_returns_none(self) -> None:
        assert strip_html_tags(None) is None

    def test_empty_string_returns_empty(self) -> None:
        assert strip_html_tags("") == ""

    def test_whitespace_only_returns_empty(self) -> None:
        assert strip_html_tags("   ") == ""

    def test_whitespace_with_tags_returns_empty(self) -> None:
        assert strip_html_tags("  <br>  ") == ""


class TestStripHtmlTagsBasic:
    """Basic HTML tag removal."""

    def test_simple_paragraph(self) -> None:
        assert strip_html_tags("<p>Hello</p>") == "Hello"

    def test_nested_tags(self) -> None:
        assert strip_html_tags("<div><p><b>Bold</b></p></div>") == "Bold"

    def test_self_closing_tags(self) -> None:
        assert strip_html_tags("Line one<br/>Line two") == "Line oneLine two"

    def test_self_closing_hr(self) -> None:
        assert strip_html_tags("Before<hr>After") == "BeforeAfter"

    def test_img_tag_removed(self) -> None:
        result = strip_html_tags('<img src="x.jpg" alt="photo">Text')
        assert result == "Text"

    def test_tag_with_attributes(self) -> None:
        result = strip_html_tags('<a href="https://example.com" class="link">Click</a>')
        assert result == "Click"

    def test_multiple_tags(self) -> None:
        result = strip_html_tags("<p>One</p><p>Two</p><p>Three</p>")
        assert result == "OneTwoThree"

    def test_no_tags_plain_text(self) -> None:
        assert strip_html_tags("Just plain text") == "Just plain text"

    def test_angle_brackets_in_text(self) -> None:
        """Non-tag angle brackets should be preserved."""
        result = strip_html_tags("Use <Enter> to confirm")
        assert result == "Use  to confirm"

    def test_script_tag_removed(self) -> None:
        """strip_html_tags removes tags but not their content."""
        result = strip_html_tags("<p>Safe</p><script>alert('xss')</script>")
        assert "Safe" in result
        assert "<script>" not in result
        assert "</script>" not in result

    def test_style_tag_removed(self) -> None:
        """strip_html_tags removes tags but not their content."""
        result = strip_html_tags("<style>.x{color:red}</style><p>Text</p>")
        assert "Text" in result
        assert "<style>" not in result
        assert "</style>" not in result

    def test_comment_removed(self) -> None:
        result = strip_html_tags("Before<!-- comment -->After")
        assert result == "BeforeAfter"


class TestStripHtmlTagsEntities:
    """HTML entity decoding."""

    def test_single_quote_entity(self) -> None:
        # &#039; is the numeric entity for single quote
        inp = "&#039;decisive&#039;"
        assert strip_html_tags(inp) == "'decisive'"

    def test_named_apos_entity(self) -> None:
        inp = "'hello'"
        assert strip_html_tags(inp) == "'hello'"

    def test_ampersand_entity(self) -> None:
        inp = "Tom & Jerry"
        assert strip_html_tags(inp) == "Tom & Jerry"

    def test_double_quote_entity(self) -> None:
        # \x26 prevents formatter from converting " to "
        inp = "\x26quot;quoted\x26quot;"
        assert strip_html_tags(inp) == '"quoted"'

    def test_less_than_entity(self) -> None:
        inp = "5 < 10"
        assert strip_html_tags(inp) == "5 < 10"

    def test_greater_than_entity(self) -> None:
        inp = "10 > 5"
        assert strip_html_tags(inp) == "10 > 5"

    def test_nbsp_entity(self) -> None:
        inp = "Hello&nbsp;World"
        assert strip_html_tags(inp) == "Hello\u00a0World"

    def test_numeric_entity_8230(self) -> None:
        """&#8230; is ellipsis …"""
        inp = "Wait&#8230;"
        assert strip_html_tags(inp) == "Wait\u2026"

    def test_named_ellipsis_entity(self) -> None:
        inp = "Wait&hellip;"
        assert strip_html_tags(inp) == "Wait\u2026"

    def test_mixed_entities(self) -> None:
        inp = "It\x26#039;s \x26quot;great\x26quot; \x26amp; fun"
        assert strip_html_tags(inp) == 'It\'s "great" & fun'

    def test_entity_inside_html_tag_content(self) -> None:
        inp = "<p>It&#039;s here</p>"
        assert strip_html_tags(inp) == "It's here"

    def test_decimal_entity_for_copyright(self) -> None:
        inp = "&#169; 2024"
        assert strip_html_tags(inp) == "\u00a9 2024"

    def test_hex_entity(self) -> None:
        inp = "&#x2026;"
        assert strip_html_tags(inp) == "\u2026"


class TestStripHtmlTagsTruncation:
    """RSS truncation marker removal."""

    def test_ellipsis_in_brackets(self) -> None:
        result = strip_html_tags("Some text [...]")
        assert result == "Some text"

    def test_ellipsis_in_brackets_unicode(self) -> None:
        result = strip_html_tags("Some text […]")
        assert result == "Some text"

    def test_hellip_entity_in_brackets(self) -> None:
        result = strip_html_tags("Some text [&hellip;]")
        assert result == "Some text"

    def test_numeric_ellipsis_in_brackets(self) -> None:
        result = strip_html_tags("Some text [&#8230;]")
        assert result == "Some text"

    def test_more_marker(self) -> None:
        result = strip_html_tags("Some text (more)")
        assert result == "Some text"

    def test_continued_marker(self) -> None:
        result = strip_html_tags("Some text (continued)")
        assert result == "Some text"

    def test_plain_ellipsis(self) -> None:
        result = strip_html_tags("Some text ...")
        assert result == "Some text"

    def test_trailing_ellipsis_no_brackets(self) -> None:
        result = strip_html_tags("Truncated text...")
        assert result == "Truncated text"

    def test_marker_with_html_tags(self) -> None:
        result = strip_html_tags("<p>Text here</p>[&#8230;]")
        assert result == "Text here"

    def test_marker_case_insensitive_more(self) -> None:
        result = strip_html_tags("Text (More)")
        assert result == "Text"

    def test_marker_case_insensitive_continued(self) -> None:
        result = strip_html_tags("Text (Continued)")
        assert result == "Text"

    def test_real_world_rss_summary_1(self) -> None:
        text = (
            "Authorities in Cauca region demand &#039;decisive&#039; "
            "government action after deadly explosion on Pan-American "
            "Highway. Israeli FM Gideon Saar [&#8230;]"
        )
        result = strip_html_tags(text)
        assert "&#039;" not in result
        assert "&#8230;" not in result
        assert "[...]" not in result
        assert "\u2026" not in result
        assert "'decisive'" in result

    def test_real_world_rss_summary_2(self) -> None:
        text = (
            "Sam Altman published an open letter to the community of "
            "Tumbler Ridge, British Columbia, on Thursday, apologising "
            "for OpenAI\u2019s failure to alert law enforcement after "
            "its own systems flagged a user who went on to carry out "
            "the deadliest school shooting in Canada in nearly four "
            'decades. "I am deeply sorry that we did not [&hellip;] '
            "This story continues at The Next Web"
        )
        result = strip_html_tags(text)
        assert "&hellip;" not in result
        assert "[...]" not in result
        assert "\u2026" not in result
        assert "This story continues" in result


class TestStripHtmlTagsCombined:
    """Combined scenarios: tags + entities + truncation."""

    def test_tags_entities_and_truncation(self) -> None:
        text = "<p>It\x26#039;s \x26quot;great\x26quot;" " \x26amp; fun</p>[\x26#8230;]"
        result = strip_html_tags(text)
        assert result == 'It\'s "great" & fun'

    def test_nested_tags_with_entities(self) -> None:
        text = "<div><b>&</b> <i>italic</i></div>"
        assert strip_html_tags(text) == "& italic"

    def test_full_html_document_with_entities(self) -> None:
        text = (
            "<html><head><title>Test</title></head>"
            "<body><p>Don&#039;t worry & be happy</p>"
            "<p>More content</p>[&hellip;]</body></html>"
        )
        result = strip_html_tags(text)
        assert "Don't worry & be happy" in result
        assert "More content" in result
        assert "&hellip;" not in result
        assert "<" not in result

    def test_preserves_internal_whitespace(self) -> None:
        result = strip_html_tags("<p>Hello  world</p>")
        assert result == "Hello  world"

    def test_strips_surrounding_whitespace(self) -> None:
        result = strip_html_tags("  <p>Content</p>  ")
        assert result == "Content"


# ---------------------------------------------------------------------------
# strip_markdown() — comprehensive unit tests
# ---------------------------------------------------------------------------


class TestStripMarkdownNoneAndEmpty:
    """Edge cases: None, empty string, whitespace-only."""

    def test_none_returns_none(self) -> None:
        assert strip_markdown(None) is None

    def test_empty_string_returns_empty(self) -> None:
        assert strip_markdown("") == ""

    def test_plain_text_unchanged(self) -> None:
        assert strip_markdown("Just plain text") == "Just plain text"


class TestStripMarkdownBold:
    """Bold marker removal."""

    def test_double_asterisks(self) -> None:
        assert strip_markdown("**bold text**") == "bold text"

    def test_double_underscores(self) -> None:
        assert strip_markdown("__bold text__") == "bold text"

    def test_bold_mid_sentence(self) -> None:
        result = strip_markdown("This is **very** important")
        assert result == "This is very important"

    def test_bold_in_sentence(self) -> None:
        result = strip_markdown("The **Federal Reserve** raised rates")
        assert result == "The Federal Reserve raised rates"


class TestStripMarkdownItalic:
    """Italic marker removal."""

    def test_single_asterisks(self) -> None:
        assert strip_markdown("*italic text*") == "italic text"

    def test_italic_mid_sentence(self) -> None:
        result = strip_markdown("This is *emphasized* text")
        assert result == "This is emphasized text"


class TestStripMarkdownBoldItalic:
    """Bold+italic combined marker removal."""

    def test_triple_asterisks(self) -> None:
        result = strip_markdown("***bold and italic***")
        assert result == "bold and italic"

    def test_triple_underscores(self) -> None:
        result = strip_markdown("___bold and italic___")
        assert result == "bold and italic"


class TestStripMarkdownHeadings:
    """Heading prefix removal."""

    def test_h1(self) -> None:
        assert strip_markdown("# Heading") == "Heading"

    def test_h2(self) -> None:
        assert strip_markdown("## Subheading") == "Subheading"

    def test_h3(self) -> None:
        assert strip_markdown("### Section") == "Section"

    def test_heading_mid_text(self) -> None:
        text = "Paragraph one.\n## Section Title\nParagraph two."
        result = strip_markdown(text)
        assert result == "Paragraph one.\nSection Title\nParagraph two."

    def test_heading_with_indent(self) -> None:
        result = strip_markdown("   # Indented heading")
        assert result == "Indented heading"


class TestStripMarkdownHorizontalRules:
    """Horizontal rule removal."""

    def test_triple_dash(self) -> None:
        result = strip_markdown("Before\n\n---\n\nAfter")
        assert "---" not in result
        assert "Before" in result
        assert "After" in result

    def test_triple_asterisks(self) -> None:
        result = strip_markdown("Before\n\n***\n\nAfter")
        assert "***" not in result
        assert "Before" in result
        assert "After" in result

    def test_triple_underscore(self) -> None:
        result = strip_markdown("Before\n\n___\n\nAfter")
        assert "___" not in result
        assert "Before" in result
        assert "After" in result


class TestStripMarkdownBlockquotes:
    """Blockquote prefix removal."""

    def test_single_level(self) -> None:
        result = strip_markdown("> Quoted text")
        assert result == "Quoted text"

    def test_nested_level(self) -> None:
        result = strip_markdown(">> Deep quote")
        assert result == "Deep quote"

    def test_blockquote_in_article(self) -> None:
        text = "Before.\n> This is a quote.\nAfter."
        result = strip_markdown(text)
        assert "> " not in result
        assert "This is a quote." in result


class TestStripMarkdownLists:
    """List marker removal."""

    def test_unordered_dash(self) -> None:
        result = strip_markdown("- Item one\n- Item two")
        assert "- " not in result
        assert "Item one" in result
        assert "Item two" in result

    def test_unordered_asterisk(self) -> None:
        result = strip_markdown("* Item one\n* Item two")
        assert "Item one" in result
        assert "Item two" in result

    def test_ordered_list(self) -> None:
        result = strip_markdown("1. First\n2. Second\n3. Third")
        assert "1." not in result
        assert "First" in result
        assert "Second" in result
        assert "Third" in result


class TestStripMarkdownLinks:
    """Link and image syntax removal."""

    def test_inline_link(self) -> None:
        result = strip_markdown("[click here](https://example.com)")
        assert result == "click here"

    def test_image(self) -> None:
        result = strip_markdown("![alt text](https://example.com/img.png)")
        assert result == "alt text"

    def test_link_mid_sentence(self) -> None:
        result = strip_markdown("See the [report](https://example.com) for details")
        assert result == "See the report for details"
        assert "https://" not in result

    def test_multiple_links(self) -> None:
        text = "[first](url1) and [second](url2)"
        result = strip_markdown(text)
        assert result == "first and second"


class TestStripMarkdownCode:
    """Code marker removal."""

    def test_inline_code(self) -> None:
        result = strip_markdown("Use the `print` function")
        assert result == "Use the print function"

    def test_fenced_code_block(self) -> None:
        text = "Before\n```python\nprint('hello')\n```\nAfter"
        result = strip_markdown(text)
        assert "```" not in result
        assert "print('hello')" in result
        assert "Before" in result
        assert "After" in result

    def test_fenced_block_tilde(self) -> None:
        text = "Before\n~~~\ncode here\n~~~\nAfter"
        result = strip_markdown(text)
        assert "~~~" not in result
        assert "code here" in result


class TestStripMarkdownStrikethrough:
    """Strikethrough marker removal."""

    def test_strikethrough(self) -> None:
        result = strip_markdown("This is ~~deleted~~ text")
        assert result == "This is deleted text"


class TestStripMarkdownCombined:
    """Combined markdown patterns."""

    def test_article_with_multiple_formats(self) -> None:
        text = (
            "## Title Here\n\n"
            "This is **bold** and *italic* text with "
            "[a link](https://example.com).\n\n"
            "- Item one\n"
            "- Item two\n\n"
            "> A blockquote\n\n"
            "---\n\n"
            "Final paragraph."
        )
        result = strip_markdown(text)
        assert "**" not in result
        assert "*" not in result.replace("Item", "Item")
        assert "[" not in result
        assert "](https" not in result
        assert "> " not in result
        assert "---" not in result
        assert "Title Here" in result
        assert "bold" in result
        assert "italic" in result
        assert "Item one" in result
        assert "A blockquote" in result
        assert "Final paragraph." in result

    def test_real_world_llm_output(self) -> None:
        """Simulate typical LLM markdown contamination."""
        text = (
            "# Breaking: Major Policy Shift\n\n"
            "The government **announced** a *sweeping* reform "
            "package on Tuesday.\n\n"
            "## Key Changes\n\n"
            "- Tax rates will increase by 2%\n"
            "- Healthcare spending rises\n\n"
            "> This is a historic moment, said the PM.\n\n"
            "See [the full report](https://gov.example.com/report) "
            "for details."
        )
        result = strip_markdown(text)
        assert "**" not in result
        assert "*sweeping*" not in result
        assert "# " not in result
        assert "- " not in result
        assert "> " not in result
        assert "[the full report]" not in result
        assert "(https://" not in result
        assert "Breaking: Major Policy Shift" in result
        assert "announced" in result
        assert "sweeping" in result
        assert "Tax rates" in result
        assert "historic moment" in result
        assert "the full report" in result

    def test_collapses_excessive_blank_lines(self) -> None:
        text = "Paragraph one.\n\n\n\n\nParagraph two."
        result = strip_markdown(text)
        assert "\n\n\n" not in result
        assert "Paragraph one." in result
        assert "Paragraph two." in result


# ---------------------------------------------------------------------------
# Integration: update_article() strips markdown from persisted content
# ---------------------------------------------------------------------------


class TestUpdateArticleStripsMarkdown:
    """Verify update_article() strips markdown from content/title/summary."""

    @pytest.fixture()
    def article_id(self, db_session) -> int:
        """Create a test article using the SQLAlchemy session fixture."""
        from news48.core.database.models import Article, Feed, Fetch

        feed = Feed(
            url="https://example.com/feed-md.xml",
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
            url="https://example.com/test-md",
            title="Test",
            summary=None,
            content="Test content",
            created_at="2024-01-01T00:00:00+00:00",
        )
        db_session.add(article)
        db_session.flush()
        return article.id

    def test_strips_bold_from_content(self, article_id: int) -> None:
        from news48.core.database.articles import get_article_by_id, update_article

        update_article(
            article_id,
            content="The **Federal Reserve** raised rates today.",
        )
        article = get_article_by_id(article_id)
        assert "**" not in article["content"]
        assert "Federal Reserve" in article["content"]

    def test_strips_headings_from_content(self, article_id: int) -> None:
        from news48.core.database.articles import get_article_by_id, update_article

        update_article(
            article_id,
            content="# Heading\n\nThe actual content here.",
        )
        article = get_article_by_id(article_id)
        assert "# " not in article["content"]
        assert "Heading" in article["content"]

    def test_strips_links_from_content(self, article_id: int) -> None:
        from news48.core.database.articles import get_article_by_id, update_article

        update_article(
            article_id,
            content="See the [report](https://example.com) for more.",
        )
        article = get_article_by_id(article_id)
        assert "[report]" not in article["content"]
        assert "report" in article["content"]

    def test_strips_bold_from_title(self, article_id: int) -> None:
        from news48.core.database.articles import get_article_by_id, update_article

        update_article(
            article_id,
            content="clean",
            title="**Breaking**: Major Reform Announced",
        )
        article = get_article_by_id(article_id)
        assert "**" not in article["title"]
        assert "Breaking" in article["title"]

    def test_strips_markdown_from_summary(self, article_id: int, db_session) -> None:
        from news48.core.database.articles import get_article_by_id, update_article
        from news48.core.database.models import Article

        # Clear existing summary so SD-1 allows the update
        art = db_session.get(Article, article_id)
        if art:
            art.summary = None
            db_session.commit()

        update_article(
            article_id,
            content="clean",
            summary="The **government** announced *sweeping* reforms.",
        )
        article = get_article_by_id(article_id)
        assert "**" not in article["summary"]
        assert "*sweeping*" not in article["summary"]
        assert "government" in article["summary"]
        assert "sweeping" in article["summary"]
