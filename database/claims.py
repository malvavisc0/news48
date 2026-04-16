"""Claims database operations — per-claim fact-check results."""

import json
from datetime import datetime, timezone
from pathlib import Path

from .connection import get_connection


def _utcnow() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def insert_claims(db_path: Path, article_id: int, claims: list[dict]) -> int:
    """Insert per-claim fact-check results for an article.

    Deletes existing claims first (idempotent re-check).
    Returns number of claims inserted.

    Args:
        db_path: Path to the SQLite database file.
        article_id: The article ID to associate claims with.
        claims: List of dicts with keys: claim_text, verdict,
                evidence_summary, sources (list or JSON string).

    Returns:
        Number of claims inserted.
    """
    delete_claims_for_article(db_path, article_id)

    now = _utcnow()
    inserted = 0

    with get_connection(db_path) as db:
        for claim in claims:
            sources = claim.get("sources", [])
            if isinstance(sources, list):
                sources_json = json.dumps(sources)
            else:
                sources_json = sources

            db.execute(
                """INSERT INTO claims
                   (article_id, claim_text, verdict,
                    evidence_summary, sources, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    article_id,
                    claim["claim_text"],
                    claim["verdict"],
                    claim.get("evidence_summary"),
                    sources_json,
                    now,
                ),
            )
            inserted += 1
        db.commit()

    return inserted


def get_claims_for_article(db_path: Path, article_id: int) -> list[dict]:
    """Return all claims for an article, ordered by id.

    Args:
        db_path: Path to the SQLite database file.
        article_id: The article ID to fetch claims for.

    Returns:
        List of dicts with keys: id, article_id, claim_text, verdict,
        evidence_summary, sources (parsed list), created_at.
    """
    with get_connection(db_path) as db:
        rows = db.execute(
            "SELECT id, article_id, claim_text, verdict, "
            "evidence_summary, sources, created_at "
            "FROM claims WHERE article_id = ? ORDER BY id",
            (article_id,),
        ).fetchall()

    result = []
    for row in rows:
        sources_raw = row["sources"]
        try:
            sources = json.loads(sources_raw) if sources_raw else []
        except (json.JSONDecodeError, TypeError):
            sources = []

        result.append(
            {
                "id": row["id"],
                "article_id": row["article_id"],
                "claim_text": row["claim_text"],
                "verdict": row["verdict"],
                "evidence_summary": row["evidence_summary"],
                "sources": sources,
                "created_at": row["created_at"],
            }
        )

    return result


def delete_claims_for_article(db_path: Path, article_id: int) -> int:
    """Delete all claims for an article. Returns count deleted.

    Args:
        db_path: Path to the SQLite database file.
        article_id: The article ID to delete claims for.

    Returns:
        Number of claims deleted.
    """
    with get_connection(db_path) as db:
        cursor = db.execute(
            "SELECT COUNT(*) FROM claims WHERE article_id = ?",
            (article_id,),
        )
        count = cursor.fetchone()[0]

        db.execute(
            "DELETE FROM claims WHERE article_id = ?",
            (article_id,),
        )
        db.commit()

    return count


def compute_overall_verdict(claims: list[dict]) -> str:
    """Derive the overall article verdict from per-claim verdicts.

    Rules:
    - All verified -> verified
    - Any disputed -> disputed
    - Mix of verified + mixed/unverifiable -> mixed
    - All unverifiable -> unverifiable

    Args:
        claims: List of claim dicts, each with a 'verdict' key.

    Returns:
        Overall verdict string.
    """
    if not claims:
        return "unverifiable"

    verdicts = {c["verdict"] for c in claims}

    if verdicts == {"verified"}:
        return "verified"

    if "disputed" in verdicts:
        return "disputed"

    if "verified" in verdicts and verdicts & {"mixed", "unverifiable"}:
        return "mixed"

    if verdicts == {"unverifiable"}:
        return "unverifiable"

    # Fallback for any other combination
    if "mixed" in verdicts:
        return "mixed"

    return "mixed"
