"""Tests for claims database operations using SQLAlchemy session fixture."""

from database import (
    claim_articles_for_processing,
    clear_article_processing_claim,
    compute_overall_verdict,
    delete_claims_for_article,
    get_article_by_id,
    get_claims_for_article,
    insert_claims,
    update_article_fact_check,
)
from database.models import Article, Feed, Fetch


def _create_article(db_session, url: str = "https://example.com/a") -> int:
    """Create a test article using the session fixture."""
    feed = Feed(
        url="https://example.com/feed.xml",
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
