from pathlib import Path

from database import (
    claim_articles_for_processing,
    clear_article_processing_claim,
    get_article_by_id,
    init_database,
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
                   fetch_id, feed_id, url, title, content, parsed_at, created_at
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
