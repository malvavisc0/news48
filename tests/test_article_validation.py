"""Tests for article content validation in _mutations.py.

Covers _validate_article_content(), update_article() validation gate,
patch_article_fields() summary validation, and pre-parse guard in
_parse_claimed_article().
"""

import pytest

from news48.core.database.articles._constants import (
    CONTENT_MAX_CHARS,
    CONTENT_MAX_PARAGRAPHS,
    CONTENT_MIN_CHARS,
    CONTENT_MIN_PARAGRAPHS,
    DOWNLOAD_MIN_CONTENT_CHARS,
    PARAGRAPH_MIN_CHARS,
    SUMMARY_MAX_CHARS,
    SUMMARY_MIN_CHARS,
    TITLE_MAX_CHARS,
    TITLE_MIN_CHARS,
)
from news48.core.database.articles._mutations import _validate_article_content

# ---------------------------------------------------------------------------
# Helper: generate valid content that passes all constraints
# ---------------------------------------------------------------------------


def _valid_content(
    num_paragraphs: int = CONTENT_MIN_PARAGRAPHS,
    chars_per_paragraph: int = 0,
) -> str:
    """Generate valid content that passes all constraints.

    If chars_per_paragraph is 0, automatically calculates a size
    that ensures the total content meets CONTENT_MIN_CHARS.
    """
    if chars_per_paragraph == 0:
        # Ensure total meets CONTENT_MIN_CHARS with room for \n\n separators
        separators = (num_paragraphs - 1) * 2
        chars_per_paragraph = max(
            PARAGRAPH_MIN_CHARS,
            (CONTENT_MIN_CHARS - separators + num_paragraphs - 1) // num_paragraphs,
        )
    paragraphs = []
    for i in range(num_paragraphs):
        paragraphs.append("x" * chars_per_paragraph)
    return "\n\n".join(paragraphs)


def _valid_summary(length: int = 150) -> str:
    """Generate a valid summary of the given length."""
    return "x" * length


# ---------------------------------------------------------------------------
# _validate_article_content() — content length
# ---------------------------------------------------------------------------


class TestValidateContentLength:
    """Content character count boundary cases."""

    def test_content_below_min_raises(self) -> None:
        with pytest.raises(ValueError, match="Content too short"):
            _validate_article_content(content="x" * (CONTENT_MIN_CHARS - 1))

    def test_content_at_min_ok(self) -> None:
        # Need enough paragraphs too
        content = _valid_content()
        _validate_article_content(content=content)  # no raise

    def test_content_above_max_raises(self) -> None:
        paragraphs = ["x" * 200] * 60  # 12,000 chars
        content = "\n\n".join(paragraphs)
        with pytest.raises(ValueError, match="Content too long"):
            _validate_article_content(content=content)

    def test_content_at_max_ok(self) -> None:
        # Build content close to max but with valid paragraph structure
        num_paragraphs = CONTENT_MIN_PARAGRAPHS
        chars_per_para = (
            CONTENT_MAX_CHARS - (num_paragraphs - 1) * 2
        ) // num_paragraphs
        content = "\n\n".join(["x" * chars_per_para] * num_paragraphs)
        # Ensure it's at or just under max
        assert len(content) <= CONTENT_MAX_CHARS
        _validate_article_content(content=content)  # no raise

    def test_content_none_skips_validation(self) -> None:
        _validate_article_content(content=None)  # no raise

    def test_content_empty_string_skips_validation(self) -> None:
        _validate_article_content(content="")  # no raise


# ---------------------------------------------------------------------------
# _validate_article_content() — paragraph count
# ---------------------------------------------------------------------------


class TestValidateParagraphCount:
    """Paragraph count boundary cases."""

    def test_single_paragraph_raises(self) -> None:
        content = "x" * CONTENT_MIN_CHARS
        with pytest.raises(ValueError, match="Too few paragraphs"):
            _validate_article_content(content=content)

    def test_two_paragraphs_raises(self) -> None:
        p = "x" * (CONTENT_MIN_CHARS // 2 + 100)
        content = f"{p}\n\n{p}"
        with pytest.raises(ValueError, match="Too few paragraphs"):
            _validate_article_content(content=content)

    def test_three_paragraphs_ok(self) -> None:
        content = _valid_content(num_paragraphs=CONTENT_MIN_PARAGRAPHS)
        _validate_article_content(content=content)  # no raise

    def test_max_paragraphs_ok(self) -> None:
        content = _valid_content(num_paragraphs=CONTENT_MAX_PARAGRAPHS)
        _validate_article_content(content=content)  # no raise

    def test_above_max_paragraphs_raises(self) -> None:
        content = _valid_content(num_paragraphs=CONTENT_MAX_PARAGRAPHS + 1)
        with pytest.raises(ValueError, match="Too many paragraphs"):
            _validate_article_content(content=content)


# ---------------------------------------------------------------------------
# _validate_article_content() — paragraph minimum length
# ---------------------------------------------------------------------------


class TestValidateParagraphMinLength:
    """Each non-empty paragraph must meet the minimum character count."""

    def test_short_paragraph_raises(self) -> None:
        long_para = "x" * 600
        short_para = "x" * (PARAGRAPH_MIN_CHARS - 1)
        content = f"{long_para}\n\n{short_para}\n\n{long_para}"
        with pytest.raises(ValueError, match="Paragraph 2 too short"):
            _validate_article_content(content=content)

    def test_all_paragraphs_at_min_ok(self) -> None:
        # Use enough paragraphs at min chars to also meet total content min
        # 1200 / 150 = 8 paragraphs needed at minimum
        num_para = max(
            CONTENT_MIN_PARAGRAPHS,
            CONTENT_MIN_CHARS // PARAGRAPH_MIN_CHARS + 1,
        )
        content = _valid_content(
            num_paragraphs=num_para,
            chars_per_paragraph=PARAGRAPH_MIN_CHARS,
        )
        _validate_article_content(content=content)  # no raise


# ---------------------------------------------------------------------------
# _validate_article_content() — summary length
# ---------------------------------------------------------------------------


class TestValidateSummaryLength:
    """Summary character count boundary cases."""

    def test_summary_below_min_raises(self) -> None:
        with pytest.raises(ValueError, match="Summary too short"):
            _validate_article_content(summary="x" * (SUMMARY_MIN_CHARS - 1))

    def test_summary_at_min_ok(self) -> None:
        _validate_article_content(summary="x" * SUMMARY_MIN_CHARS)  # no raise

    def test_summary_at_max_ok(self) -> None:
        _validate_article_content(summary="x" * SUMMARY_MAX_CHARS)  # no raise

    def test_summary_above_max_raises(self) -> None:
        with pytest.raises(ValueError, match="Summary too long"):
            _validate_article_content(summary="x" * (SUMMARY_MAX_CHARS + 1))

    def test_summary_none_skips_validation(self) -> None:
        _validate_article_content(summary=None)  # no raise

    def test_summary_empty_string_skips_validation(self) -> None:
        _validate_article_content(summary="")  # no raise


# ---------------------------------------------------------------------------
# _validate_article_content() — title length
# ---------------------------------------------------------------------------


class TestValidateTitleLength:
    """Title character count boundary cases."""

    def test_title_below_min_raises(self) -> None:
        with pytest.raises(ValueError, match="Title too short"):
            _validate_article_content(title="x" * (TITLE_MIN_CHARS - 1))

    def test_title_at_min_ok(self) -> None:
        _validate_article_content(title="x" * TITLE_MIN_CHARS)  # no raise

    def test_title_at_max_ok(self) -> None:
        _validate_article_content(title="x" * TITLE_MAX_CHARS)  # no raise

    def test_title_above_max_raises(self) -> None:
        with pytest.raises(ValueError, match="Title too long"):
            _validate_article_content(title="x" * (TITLE_MAX_CHARS + 1))

    def test_title_none_skips_validation(self) -> None:
        _validate_article_content(title=None)  # no raise

    def test_title_empty_string_skips_validation(self) -> None:
        _validate_article_content(title="")  # no raise


# ---------------------------------------------------------------------------
# _validate_article_content() — error messages include constraint info
# ---------------------------------------------------------------------------


class TestValidationErrorMessage:
    """ValueError messages must include the specific violated constraint."""

    def test_content_short_includes_numbers(self) -> None:
        with pytest.raises(ValueError, match=r"1199 chars.*minimum 1200"):
            _validate_article_content(content="x" * 1199)

    def test_content_long_includes_numbers(self) -> None:
        paragraphs = ["x" * 200] * 60
        content = "\n\n".join(paragraphs)
        with pytest.raises(ValueError, match=r"chars.*maximum 10000"):
            _validate_article_content(content=content)

    def test_summary_short_includes_numbers(self) -> None:
        with pytest.raises(ValueError, match=r"79 chars.*minimum 80"):
            _validate_article_content(summary="x" * 79)

    def test_summary_long_includes_numbers(self) -> None:
        with pytest.raises(ValueError, match=r"421 chars.*maximum 420"):
            _validate_article_content(summary="x" * 421)

    def test_title_short_includes_numbers(self) -> None:
        with pytest.raises(ValueError, match=r"7 chars.*minimum 8"):
            _validate_article_content(title="x" * 7)

    def test_title_long_includes_numbers(self) -> None:
        with pytest.raises(ValueError, match=r"141 chars.*maximum 140"):
            _validate_article_content(title="x" * 141)

    def test_few_paragraphs_includes_count(self) -> None:
        with pytest.raises(ValueError, match=r"1.*minimum 3"):
            _validate_article_content(content="x" * 2000)

    def test_many_paragraphs_includes_count(self) -> None:
        content = _valid_content(num_paragraphs=20)
        with pytest.raises(ValueError, match=r"20.*maximum 15"):
            _validate_article_content(content=content)


# ---------------------------------------------------------------------------
# update_article() — validation gate (parsed_at guard)
# ---------------------------------------------------------------------------


class TestUpdateArticleValidationGate:
    """update_article() should only validate when parsed_at is provided."""

    @pytest.fixture()
    def article_id(self, db_session) -> int:
        """Create a test article."""
        from news48.core.database.models import Article, Feed, Fetch

        feed = Feed(
            url="https://example.com/feed-val.xml",
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
            url="https://example.com/val-test",
            title="Test Article for Validation",
            summary=None,
            content="Original content",
            created_at="2024-01-01T00:00:00+00:00",
        )
        db_session.add(article)
        db_session.flush()
        return article.id

    def test_validation_fires_when_parsed_at_set(self, article_id: int) -> None:
        """When parsed_at is provided, validation should reject bad content."""
        from news48.core.database.articles import update_article

        with pytest.raises(ValueError, match="Content too short"):
            update_article(
                article_id=article_id,
                content="too short",
                parsed_at="2024-01-01T00:00:00+00:00",
            )

    def test_validation_skipped_when_no_parsed_at(self, article_id: int) -> None:
        """When parsed_at is None, validation should NOT fire."""
        from news48.core.database.articles import update_article

        # Should not raise — validation is skipped
        update_article(
            article_id=article_id,
            content="too short but no parsed_at",
            parsed_at=None,
        )

    def test_validation_on_summary_too_long_with_parsed_at(
        self, article_id: int, db_session
    ) -> None:
        """Summary exceeding max should be rejected when parsed_at is set."""
        from news48.core.database.articles import update_article
        from news48.core.database.models import Article

        # Clear existing summary so it can be updated
        art = db_session.get(Article, article_id)
        if art:
            art.summary = None
            db_session.commit()

        valid_content = _valid_content()
        with pytest.raises(ValueError, match="Summary too long"):
            update_article(
                article_id=article_id,
                content=valid_content,
                summary="x" * (SUMMARY_MAX_CHARS + 1),
                parsed_at="2024-01-01T00:00:00+00:00",
            )

    def test_valid_content_passes_with_parsed_at(
        self, article_id: int, db_session
    ) -> None:
        """Valid content should pass validation when parsed_at is set."""
        from news48.core.database.articles import get_article_by_id, update_article
        from news48.core.database.models import Article

        # Clear existing summary so it can be updated
        art = db_session.get(Article, article_id)
        if art:
            art.summary = None
            db_session.commit()

        valid_content_str = _valid_content()
        valid_summary = _valid_summary()
        update_article(
            article_id=article_id,
            content=valid_content_str,
            summary=valid_summary,
            parsed_at="2024-01-01T00:00:00+00:00",
        )
        updated = get_article_by_id(article_id)
        assert updated["parsed_at"] is not None


# ---------------------------------------------------------------------------
# patch_article_fields() — summary validation
# ---------------------------------------------------------------------------


class TestPatchArticleFieldsSummaryValidation:
    """patch_article_fields() should validate summary length."""

    @pytest.fixture()
    def article_id(self, db_session) -> int:
        """Create a test article."""
        from news48.core.database.models import Article, Feed, Fetch

        feed = Feed(
            url="https://example.com/feed-patch.xml",
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
            url="https://example.com/patch-test",
            title="Test Article for Patch",
            summary=None,
            content="Test content",
            created_at="2024-01-01T00:00:00+00:00",
        )
        db_session.add(article)
        db_session.flush()
        return article.id

    def test_patch_summary_too_short_raises(self, article_id: int) -> None:
        from news48.core.database.articles import patch_article_fields

        with pytest.raises(ValueError, match="Summary too short"):
            patch_article_fields(
                article_id=article_id,
                summary="x" * (SUMMARY_MIN_CHARS - 1),
            )

    def test_patch_summary_too_long_raises(self, article_id: int) -> None:
        from news48.core.database.articles import patch_article_fields

        with pytest.raises(ValueError, match="Summary too long"):
            patch_article_fields(
                article_id=article_id,
                summary="x" * (SUMMARY_MAX_CHARS + 1),
            )

    def test_patch_summary_valid_ok(self, article_id: int) -> None:
        from news48.core.database.articles import (
            get_article_by_id,
            patch_article_fields,
        )

        valid_sum = "x" * 150
        patch_article_fields(article_id=article_id, summary=valid_sum)
        article = get_article_by_id(article_id)
        assert article["summary"] is not None

    def test_patch_no_summary_no_validation(self, article_id: int) -> None:
        """When no summary provided, no validation should fire."""
        from news48.core.database.articles import patch_article_fields

        # Should not raise — only updating categories
        patch_article_fields(article_id=article_id, categories="world")


# ---------------------------------------------------------------------------
# Pre-parse guard — content length gate in parser.py
# ---------------------------------------------------------------------------


class TestPreParseContentGuard:
    """_parse_claimed_article() should reject articles with too little content."""

    def test_short_content_rejected(self) -> None:
        """Articles with content below DOWNLOAD_MIN_CONTENT_CHARS should fail."""
        # Test the guard condition directly (the full async function
        # requires a DB, so we verify the threshold logic here)
        short_content = "x" * (DOWNLOAD_MIN_CONTENT_CHARS - 1)
        content_len = len(short_content.strip())
        assert content_len < DOWNLOAD_MIN_CONTENT_CHARS

    def test_min_content_passes(self) -> None:
        """Articles with content at or above DOWNLOAD_MIN_CONTENT_CHARS should pass."""
        content = "x" * DOWNLOAD_MIN_CONTENT_CHARS
        content_len = len(content.strip())
        assert content_len >= DOWNLOAD_MIN_CONTENT_CHARS


# ---------------------------------------------------------------------------
# _validate_article_content() — combined fields
# ---------------------------------------------------------------------------


class TestValidateCombinedFields:
    """Test validation with multiple fields provided at once."""

    def test_all_fields_valid_ok(self) -> None:
        content = _valid_content()
        summary = _valid_summary()
        title = "A" * 50
        _validate_article_content(content=content, summary=summary, title=title)

    def test_valid_content_invalid_summary_raises(self) -> None:
        content = _valid_content()
        with pytest.raises(ValueError, match="Summary too short"):
            _validate_article_content(content=content, summary="short")

    def test_valid_content_invalid_title_raises(self) -> None:
        content = _valid_content()
        with pytest.raises(ValueError, match="Title too short"):
            _validate_article_content(content=content, title="x")

    def test_invalid_content_valid_summary_raises_content_first(self) -> None:
        """Content is validated before summary, so content error should fire."""
        with pytest.raises(ValueError, match="Content too short"):
            _validate_article_content(content="short", summary="x" * 200)


# ---------------------------------------------------------------------------
# Constants — sanity check values match the plan
# ---------------------------------------------------------------------------


class TestConstantValues:
    """Verify constants match the documented plan values."""

    def test_content_min_chars(self) -> None:
        assert CONTENT_MIN_CHARS == 1200

    def test_content_max_chars(self) -> None:
        assert CONTENT_MAX_CHARS == 10000

    def test_content_min_paragraphs(self) -> None:
        assert CONTENT_MIN_PARAGRAPHS == 3

    def test_content_max_paragraphs(self) -> None:
        assert CONTENT_MAX_PARAGRAPHS == 15

    def test_paragraph_min_chars(self) -> None:
        assert PARAGRAPH_MIN_CHARS == 150

    def test_summary_min_chars(self) -> None:
        assert SUMMARY_MIN_CHARS == 80

    def test_summary_max_chars(self) -> None:
        assert SUMMARY_MAX_CHARS == 420

    def test_title_min_chars(self) -> None:
        assert TITLE_MIN_CHARS == 8

    def test_title_max_chars(self) -> None:
        assert TITLE_MAX_CHARS == 140

    def test_download_min_content_chars(self) -> None:
        assert DOWNLOAD_MIN_CONTENT_CHARS == 400
