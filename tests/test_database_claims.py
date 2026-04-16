from pathlib import Path

from database import (
    claim_articles_for_processing,
    clear_article_processing_claim,
    compute_overall_verdict,
    delete_claims_for_article,
    get_article_by_id,
    get_claims_for_article,
    init_database,
    insert_claims,
    seed_feeds,
    update_article_fact_check,
)


def _create_article(db_path: Path, url: str = "https://example.com/a") -> int:
    seed_feeds(db_path, ["https://example.com/feed.xml"])
    from database import get_connection

    with get_connection(db_path) as db:
        feed_id = db.execute("SELECT id FROM feeds LIMIT 1").fetchone()[0]
        fetch_id = db.execute(
            "INSERT INTO fetches (started_at, status) VALUES (?, ?)",
            ("2024-01-01T00:00:00+00:00", "running"),
        ).lastrowid
        article_id = db.execute(
            """INSERT INTO articles (
                   fetch_id, feed_id, url, title, content,
                   parsed_at, created_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                fetch_id,
                feed_id,
                url,
                "Example",
                "content",
                "2024-01-01T00:00:00+00:00",
                "2024-01-01T00:00:00+00:00",
            ),
        ).lastrowid
        db.commit()
        return int(article_id)


def test_processing_claim_prevents_second_owner(tmp_path):
    db_path = tmp_path / "claims.db"
    init_database(db_path)
    article_id = _create_article(db_path)

    claimed = claim_articles_for_processing(
        db_path,
        [article_id],
        "fact_check",
        "owner-a",
    )
    assert claimed == [article_id]

    claimed_again = claim_articles_for_processing(
        db_path,
        [article_id],
        "fact_check",
        "owner-b",
    )
    assert claimed_again == []


def test_processing_claim_can_be_released(tmp_path):
    db_path = tmp_path / "claims.db"
    init_database(db_path)
    article_id = _create_article(db_path)

    claim_articles_for_processing(db_path, [article_id], "parse", "owner-a")
    clear_article_processing_claim(db_path, article_id, owner="owner-a")

    claimed = claim_articles_for_processing(
        db_path,
        [article_id],
        "parse",
        "owner-b",
    )
    assert claimed == [article_id]


def test_update_article_fact_check_requires_force_to_overwrite(tmp_path):
    db_path = tmp_path / "claims.db"
    init_database(db_path)
    article_id = _create_article(db_path)

    updated = update_article_fact_check(
        db_path,
        article_id,
        status="verified",
        result="ok",
    )
    assert updated is True

    updated_without_force = update_article_fact_check(
        db_path,
        article_id,
        status="disputed",
        result="changed",
    )
    assert updated_without_force is False

    updated_with_force = update_article_fact_check(
        db_path,
        article_id,
        status="disputed",
        result="changed",
        force=True,
    )
    assert updated_with_force is True

    article = get_article_by_id(db_path, article_id)
    assert article["fact_check_status"] == "disputed"
    assert article["fact_check_result"] == "changed"


def test_insert_claims_creates_records(tmp_path):
    db_path = tmp_path / "claims.db"
    init_database(db_path)
    article_id = _create_article(db_path)

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

    count = insert_claims(db_path, article_id, claims)
    assert count == 2

    retrieved = get_claims_for_article(db_path, article_id)
    assert len(retrieved) == 2
    assert retrieved[0]["claim_text"] == "The sky is blue"
    assert retrieved[0]["verdict"] == "verified"
    assert retrieved[1]["claim_text"] == "Grass is red"
    assert retrieved[1]["verdict"] == "disputed"


def test_insert_claims_replaces_on_recheck(tmp_path):
    db_path = tmp_path / "claims.db"
    init_database(db_path)
    article_id = _create_article(db_path)

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
    insert_claims(db_path, article_id, first_claims)
    assert len(get_claims_for_article(db_path, article_id)) == 2

    second_claims = [
        {
            "claim_text": "New claim",
            "verdict": "disputed",
            "evidence_summary": "",
            "sources": [],
        },
    ]
    insert_claims(db_path, article_id, second_claims)

    retrieved = get_claims_for_article(db_path, article_id)
    assert len(retrieved) == 1
    assert retrieved[0]["claim_text"] == "New claim"


def test_get_claims_for_article_returns_ordered(tmp_path):
    db_path = tmp_path / "claims.db"
    init_database(db_path)
    article_id = _create_article(db_path)

    claims = [
        {
            "claim_text": f"Claim {i}",
            "verdict": "verified",
            "evidence_summary": "",
            "sources": [],
        }
        for i in range(5)
    ]
    insert_claims(db_path, article_id, claims)

    retrieved = get_claims_for_article(db_path, article_id)
    assert len(retrieved) == 5
    for i, c in enumerate(retrieved):
        assert c["claim_text"] == f"Claim {i}"


def test_delete_claims_for_article_removes_all(tmp_path):
    db_path = tmp_path / "claims.db"
    init_database(db_path)
    article_id = _create_article(db_path)

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
    insert_claims(db_path, article_id, claims)

    deleted = delete_claims_for_article(db_path, article_id)
    assert deleted == 3

    retrieved = get_claims_for_article(db_path, article_id)
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
