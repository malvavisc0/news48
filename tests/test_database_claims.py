"""Tests for claims database operations using SQLAlchemy session fixture."""

from datetime import datetime, timedelta, timezone

from database import (
    claim_articles_for_processing,
    clear_article_processing_claim,
    compute_overall_verdict,
    delete_claims_for_article,
    get_article_by_id,
    get_articles_paginated,
    get_claims_for_article,
    get_web_stats,
    insert_claims,
    update_article_fact_check,
)
from database.articles import (
    get_articles_by_category,
    get_articles_by_tag,
    release_stale_article_claims,
)
from database.models import Article, Feed, Fetch


def _create_article(db_session, url: str = "https://example.com/a") -> int:
    """Create a test article using the session fixture."""
    suffix = url.rsplit("/", 1)[-1]
    feed = Feed(
        url=f"https://example.com/{suffix}-feed.xml",
        created_at="2024-01-01T00:00:00+00:00",
    )
    db_session.add(feed)
    db_session.flush()

    fetch = Fetch(started_at="2024-01-01T00:00:00+00:00", status="running")
    db_session.add(fetch)
    db_session.flush()

    article = Article(
        fetch_id=fetch.id,
        feed_id=feed.id,
        url=url,
        title="Example",
        content="content",
        parsed_at="2024-01-01T00:00:00+00:00",
        created_at="2024-01-01T00:00:00+00:00",
    )
    db_session.add(article)
    db_session.flush()
    return article.id


def test_processing_claim_prevents_second_owner(db_session):
    article_id = _create_article(db_session)

    claimed = claim_articles_for_processing(
        [article_id],
        "fact_check",
        "owner-a",
    )
    assert claimed == [article_id]

    claimed_again = claim_articles_for_processing(
        [article_id],
        "fact_check",
        "owner-b",
    )
    assert claimed_again == []


def test_processing_claim_can_be_released(db_session):
    article_id = _create_article(db_session)

    claim_articles_for_processing([article_id], "parse", "owner-a")
    clear_article_processing_claim(article_id, owner="owner-a")

    claimed = claim_articles_for_processing(
        [article_id],
        "parse",
        "owner-b",
    )
    assert claimed == [article_id]


def test_release_stale_article_claims_releases_download_claims(db_session):
    article_id = _create_article(db_session)

    claim_articles_for_processing([article_id], "download", "owner-a")

    article = db_session.get(Article, article_id)
    article.processing_started_at = (
        datetime.now(timezone.utc) - timedelta(minutes=31)
    ).isoformat()
    db_session.commit()

    result = release_stale_article_claims()
    assert result["released"] == 1

    refreshed = get_article_by_id(article_id)
    assert refreshed is not None
    assert refreshed["processing_status"] is None
    assert refreshed["processing_owner"] is None
    assert refreshed["processing_started_at"] is None


def test_get_web_stats_uses_latest_parsed_timestamp_for_parsed_view(
    db_session,
):
    old_article_id = _create_article(db_session, url="https://example.com/old")
    new_article_id = _create_article(db_session, url="https://example.com/new")

    old_article = db_session.get(Article, old_article_id)
    new_article = db_session.get(Article, new_article_id)
    assert old_article is not None
    assert new_article is not None

    old_article.created_at = "2024-01-01T00:10:00+00:00"
    old_article.parsed_at = "2024-01-01T00:20:00+00:00"
    new_article.created_at = "2024-01-01T00:40:00+00:00"
    new_article.parsed_at = "2024-01-01T00:30:00+00:00"
    db_session.commit()

    stats = get_web_stats(hours=999999, parsed=True)
    assert stats["last_updated"] == "2024-01-01T00:30:00+00:00"


def test_get_articles_by_category_without_limit_returns_all_matches(
    db_session,
):
    first_id = _create_article(db_session, url="https://example.com/cat-1")
    second_id = _create_article(db_session, url="https://example.com/cat-2")

    first = db_session.get(Article, first_id)
    second = db_session.get(Article, second_id)
    assert first is not None
    assert second is not None

    first.categories = "world"
    second.categories = "world"
    db_session.commit()

    articles, total = get_articles_by_category("world", hours=999999, limit=None)
    assert total == 2
    assert len(articles) == 2


def test_get_articles_by_tag_without_limit_returns_all_matches(db_session):
    first_id = _create_article(db_session, url="https://example.com/tag-1")
    second_id = _create_article(db_session, url="https://example.com/tag-2")

    first = db_session.get(Article, first_id)
    second = db_session.get(Article, second_id)
    assert first is not None
    assert second is not None

    first.tags = "europe"
    second.tags = "europe"
    db_session.commit()

    articles, total = get_articles_by_tag("europe", hours=999999, limit=None)
    assert total == 2
    assert len(articles) == 2


def test_get_articles_paginated_respects_requested_limit(db_session):
    ids = [
        _create_article(db_session, url=f"https://example.com/home-{i}")
        for i in range(40)
    ]

    for idx, article_id in enumerate(ids):
        article = db_session.get(Article, article_id)
        assert article is not None
        article.created_at = f"2024-01-01T00:{idx:02d}:00+00:00"
        article.parsed_at = f"2024-01-01T00:{idx:02d}:30+00:00"
    db_session.commit()

    articles, total = get_articles_paginated(hours=999999, limit=35, parsed=True)
    assert total == 40
    assert len(articles) == 35


def test_update_article_fact_check_requires_force_to_overwrite(db_session):
    article_id = _create_article(db_session)

    updated = update_article_fact_check(
        article_id,
        status="verified",
        result="ok",
    )
    assert updated is True

    updated_without_force = update_article_fact_check(
        article_id,
        status="disputed",
        result="changed",
    )
    assert updated_without_force is False

    updated_with_force = update_article_fact_check(
        article_id,
        status="disputed",
        result="changed",
        force=True,
    )
    assert updated_with_force is True

    article = get_article_by_id(article_id)
    assert article is not None
    assert article["fact_check_status"] == "disputed"
    assert article["fact_check_result"] == "changed"


def test_insert_claims_creates_records(db_session):
    article_id = _create_article(db_session)

    claims = [
        {
            "claim_text": "The sky is blue",
            "verdict": "verified",
            "evidence_summary": "Confirmed by observation",
            "sources": ["https://example.com/1"],
        },
        {
            "claim_text": "Grass is red",
            "verdict": "disputed",
            "evidence_summary": "Contradicted by evidence",
            "sources": ["https://example.com/2"],
        },
    ]

    count = insert_claims(article_id, claims)
    assert count == 2

    retrieved = get_claims_for_article(article_id)
    assert len(retrieved) == 2
    assert retrieved[0]["claim_text"] == "The sky is blue"
    assert retrieved[0]["verdict"] == "verified"
    assert retrieved[1]["claim_text"] == "Grass is red"
    assert retrieved[1]["verdict"] == "disputed"


def test_insert_claims_replaces_on_recheck(db_session):
    article_id = _create_article(db_session)

    first_claims = [
        {
            "claim_text": "Old claim 1",
            "verdict": "verified",
            "evidence_summary": "",
            "sources": [],
        },
        {
            "claim_text": "Old claim 2",
            "verdict": "verified",
            "evidence_summary": "",
            "sources": [],
        },
    ]
    insert_claims(article_id, first_claims)
    assert len(get_claims_for_article(article_id)) == 2

    second_claims = [
        {
            "claim_text": "New claim",
            "verdict": "disputed",
            "evidence_summary": "",
            "sources": [],
        },
    ]
    insert_claims(article_id, second_claims)

    retrieved = get_claims_for_article(article_id)
    assert len(retrieved) == 1
    assert retrieved[0]["claim_text"] == "New claim"


def test_get_claims_for_article_returns_ordered(db_session):
    article_id = _create_article(db_session)

    claims = [
        {
            "claim_text": f"Claim {i}",
            "verdict": "verified",
            "evidence_summary": "",
            "sources": [],
        }
        for i in range(5)
    ]
    insert_claims(article_id, claims)

    retrieved = get_claims_for_article(article_id)
    assert len(retrieved) == 5
    for i, c in enumerate(retrieved):
        assert c["claim_text"] == f"Claim {i}"


def test_delete_claims_for_article_removes_all(db_session):
    article_id = _create_article(db_session)

    claims = [
        {
            "claim_text": "Claim 1",
            "verdict": "verified",
            "evidence_summary": "",
            "sources": [],
        },
        {
            "claim_text": "Claim 2",
            "verdict": "verified",
            "evidence_summary": "",
            "sources": [],
        },
        {
            "claim_text": "Claim 3",
            "verdict": "verified",
            "evidence_summary": "",
            "sources": [],
        },
    ]
    insert_claims(article_id, claims)

    deleted = delete_claims_for_article(article_id)
    assert deleted == 3

    retrieved = get_claims_for_article(article_id)
    assert len(retrieved) == 0


def test_compute_overall_verdict_all_verified():
    claims = [
        {"verdict": "verified"},
        {"verdict": "verified"},
    ]
    assert compute_overall_verdict(claims) == "verified"


def test_compute_overall_verdict_any_disputed():
    claims = [
        {"verdict": "verified"},
        {"verdict": "disputed"},
        {"verdict": "verified"},
    ]
    assert compute_overall_verdict(claims) == "disputed"


def test_compute_overall_verdict_mixed():
    claims = [
        {"verdict": "verified"},
        {"verdict": "unverifiable"},
    ]
    assert compute_overall_verdict(claims) == "mixed"


def test_compute_overall_verdict_all_unverifiable():
    claims = [
        {"verdict": "unverifiable"},
        {"verdict": "unverifiable"},
    ]
    assert compute_overall_verdict(claims) == "unverifiable"
