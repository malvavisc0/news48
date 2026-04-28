"""Tests for MCP tool handlers and shared response shaping."""

import pytest

from news48.core.database.models import Article, Feed, Fetch

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _create_article(
    db_session,
    *,
    url: str = "https://example.com/a",
    title: str = "Test Article",
    summary: str = "A test summary for the article.",
    content: str = "Full article content here.",
    categories: str = "technology",
    tags: str = "ai,machine-learning",
    countries: str | None = "us,gb",
    sentiment: str = "neutral",
    parsed_at: str = "2024-01-01T00:00:00+00:00",
    created_at: str = "2024-01-01T00:00:00+00:00",
    is_breaking: bool = False,
    fact_check_status: str | None = None,
) -> int:
    """Create a test article with full metadata."""
    suffix = url.rsplit("/", 1)[-1]
    feed = Feed(
        url=f"https://example.com/{suffix}-feed.xml",
        title=f"Feed {suffix}",
        created_at="2024-01-01T00:00:00+00:00",
    )
    db_session.add(feed)
    db_session.flush()

    fetch = Fetch(started_at="2024-01-01T00:00:00+00:00", status="completed")
    db_session.add(fetch)
    db_session.flush()

    article = Article(
        fetch_id=fetch.id,
        feed_id=feed.id,
        url=url,
        title=title,
        summary=summary,
        content=content,
        categories=categories,
        tags=tags,
        countries=countries,
        sentiment=sentiment,
        parsed_at=parsed_at,
        created_at=created_at,
        is_breaking=is_breaking,
        fact_check_status=fact_check_status,
    )
    db_session.add(article)
    db_session.flush()
    return article.id


# ---------------------------------------------------------------------------
# DB function tests
# ---------------------------------------------------------------------------


class TestGetAllCountries:
    """Test get_all_countries returns correct country counts."""

    def test_returns_country_counts(self, db_session):
        from news48.core.database.articles import get_all_countries

        _create_article(
            db_session,
            url="https://example.com/a1",
            title="US and GB story",
            countries="us,gb",
        )
        _create_article(
            db_session,
            url="https://example.com/a2",
            title="US and DE story",
            countries="us,de",
        )
        _create_article(
            db_session,
            url="https://example.com/a3",
            title="GB only story",
            countries="gb",
        )

        result = get_all_countries(hours=999999)
        counts = {c["name"]: c["article_count"] for c in result}

        assert counts["us"] == 2
        assert counts["gb"] == 2
        assert counts["de"] == 1

    def test_excludes_empty_countries(self, db_session):
        from news48.core.database.articles import get_all_countries

        _create_article(db_session, url="https://example.com/a1", countries="")
        _create_article(db_session, url="https://example.com/a2", countries=None)

        result = get_all_countries(hours=999999)
        assert result == []

    def test_deduplicates_by_title(self, db_session):
        from news48.core.database.articles import get_all_countries

        _create_article(
            db_session,
            url="https://example.com/a1",
            title="Same Story",
            countries="us",
        )
        _create_article(
            db_session,
            url="https://example.com/a2",
            title="Same Story",
            countries="us",
        )

        result = get_all_countries(hours=999999)
        counts = {c["name"]: c["article_count"] for c in result}
        assert counts["us"] == 1

    def test_sorted_by_count_desc(self, db_session):
        from news48.core.database.articles import get_all_countries

        _create_article(
            db_session,
            url="https://example.com/a1",
            title="DE story 1",
            countries="de",
        )
        _create_article(
            db_session,
            url="https://example.com/a2",
            title="US story 1",
            countries="us",
        )
        _create_article(
            db_session,
            url="https://example.com/a3",
            title="US story 2",
            countries="us",
        )
        _create_article(
            db_session,
            url="https://example.com/a4",
            title="US story 3",
            countries="us",
        )

        result = get_all_countries(hours=999999)
        assert result[0]["name"] == "us"
        assert result[0]["article_count"] == 3
        assert result[1]["name"] == "de"
        assert result[1]["article_count"] == 1


class TestGetAllCategories:
    """Test get_all_categories returns correct category counts."""

    def test_returns_category_counts(self, db_session):
        from news48.core.database.articles import get_all_categories

        _create_article(
            db_session,
            url="https://example.com/a1",
            title="Tech story",
            categories="technology",
        )
        _create_article(
            db_session,
            url="https://example.com/a2",
            title="AI story",
            categories="technology,ai",
        )

        result = get_all_categories(hours=999999)
        counts = {c["name"]: c["article_count"] for c in result}
        assert counts["technology"] == 2
        assert counts["ai"] == 1

    def test_has_slug_field(self, db_session):
        from news48.core.database.articles import get_all_categories

        _create_article(
            db_session,
            url="https://example.com/a1",
            categories="artificial intelligence",
        )

        result = get_all_categories(hours=999999)
        assert any(c["slug"] == "artificial-intelligence" for c in result)


class TestGetRelatedArticles:
    """Test get_related_articles finds articles with shared tags/categories."""

    def test_finds_related_by_tags(self, db_session):
        from news48.core.database.articles import get_related_articles

        id1 = _create_article(
            db_session,
            url="https://example.com/a1",
            tags="ai,gpt",
            categories="technology",
        )
        _create_article(
            db_session,
            url="https://example.com/a2",
            tags="ai,robotics",
            categories="science",
        )
        _create_article(
            db_session,
            url="https://example.com/a3",
            tags="sports",
            categories="sports",
        )

        related = get_related_articles(id1, limit=5)
        assert len(related) >= 1
        # a2 shares "ai" tag, should be related
        # a3 has no overlap, should not be related

    def test_excludes_self(self, db_session):
        from news48.core.database.articles import get_related_articles

        id1 = _create_article(
            db_session,
            url="https://example.com/a1",
            tags="ai",
        )

        related = get_related_articles(id1, limit=5)
        related_ids = [r["id"] for r in related]
        assert id1 not in related_ids

    def test_returns_empty_for_no_tokens(self, db_session):
        from news48.core.database.articles import get_related_articles

        id1 = _create_article(
            db_session,
            url="https://example.com/a1",
            tags="",
            categories="",
        )

        related = get_related_articles(id1, limit=5)
        assert related == []


class TestSearchArticlesCountryFilter:
    """Test search_articles with country filter."""

    @pytest.mark.skip(
        reason="search_articles uses MySQL MATCH...AGAINST, not available in SQLite"
    )
    def test_country_filter_matches(self, db_session):
        """Country LIKE filter should match articles with that country code."""
        from news48.core.database.articles import search_articles

        _create_article(
            db_session,
            url="https://example.com/a1",
            title="US Election News",
            countries="us",
            content="US election content for fulltext search",
        )
        _create_article(
            db_session,
            url="https://example.com/a2",
            title="UK Politics Update",
            countries="gb",
            content="UK politics content for fulltext search",
        )

        results, total = search_articles(
            query="election",
            hours=999999,
            country="us",
        )
        # Should only find the US article (if fulltext matches)
        for r in results:
            assert "us" in (r.get("countries") or "")


class TestGetArticlesPaginatedCountryFilter:
    """Test get_articles_paginated with country filter."""

    def test_country_filter(self, db_session):
        from news48.core.database.articles import get_articles_paginated

        _create_article(
            db_session,
            url="https://example.com/a1",
            countries="us",
        )
        _create_article(
            db_session,
            url="https://example.com/a2",
            countries="gb",
        )

        articles, total = get_articles_paginated(hours=999999, country="us")
        assert total == 1
        assert len(articles) == 1


# ---------------------------------------------------------------------------
# MCP response shaping tests
# ---------------------------------------------------------------------------


class TestCompactArticle:
    """Test _compact_article extracts correct fields."""

    def test_extracts_expected_fields(self):
        from news48.mcp.tools import _compact_article

        row = {
            "id": 1,
            "title": "Test",
            "summary": "Summary",
            "url": "https://example.com",
            "source_name": "Example",
            "published_at": "2024-01-01",
            "categories": "tech",
            "sentiment": "neutral",
            "fact_check_status": "verified",
        }
        result = _compact_article(row)
        assert result["id"] == 1
        assert result["title"] == "Test"
        assert result["source_name"] == "Example"
        assert result["fact_check_status"] == "verified"

    def test_falls_back_to_feed_source_name(self):
        from news48.mcp.tools import _compact_article

        row = {
            "id": 1,
            "title": "Test",
            "feed_source_name": "Feed Title",
        }
        result = _compact_article(row)
        assert result["source_name"] == "Feed Title"


class TestFullArticle:
    """Test _full_article includes content and extended fields."""

    def test_includes_content_and_tags(self):
        from news48.mcp.tools import _full_article

        row = {
            "id": 1,
            "title": "Test",
            "content": "Full text",
            "tags": "ai,ml",
            "countries": "us",
            "language": "en",
            "fact_check_result": "Verified",
        }
        result = _full_article(row)
        assert result["content"] == "Full text"
        assert result["tags"] == "ai,ml"
        assert result["countries"] == "us"
        assert result["language"] == "en"
        assert result["fact_check_result"] == "Verified"


class TestClampInt:
    """Test _clamp_int boundary behavior."""

    def test_clamps_to_range(self):
        from news48.mcp.tools import _clamp_int

        assert _clamp_int(5, 10, 1, 100) == 5
        assert _clamp_int(0, 10, 1, 100) == 1
        assert _clamp_int(200, 10, 1, 100) == 100

    def test_uses_default_on_none(self):
        from news48.mcp.tools import _clamp_int

        assert _clamp_int(None, 42, 1, 100) == 42

    def test_uses_default_on_non_numeric(self):
        from news48.mcp.tools import _clamp_int

        assert _clamp_int("abc", 42, 1, 100) == 42


# ---------------------------------------------------------------------------
# MCP tool count test
# ---------------------------------------------------------------------------


class TestToolDefinitions:
    """Test MCP tool registry."""

    def test_six_tools_registered(self):
        from news48.mcp.tools import TOOLS

        assert len(TOOLS) == 6

    def test_tool_names(self):
        from news48.mcp.tools import TOOLS

        names = {t.name for t in TOOLS}
        expected = {
            "get_briefing",
            "search_news",
            "get_article",
            "browse_category",
            "list_categories",
            "list_countries",
        }
        assert names == expected

    def test_all_tools_have_required_schema(self):
        from news48.mcp.tools import TOOLS

        for tool in TOOLS:
            assert tool.name
            assert tool.description
            assert "type" in tool.inputSchema
            assert tool.inputSchema["type"] == "object"
            assert "properties" in tool.inputSchema
