"""Claims database operations — per-claim fact-check results."""

import json
from datetime import datetime, timezone

from .connection import SessionLocal
from .models import Claim


def _utcnow() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def insert_claims(article_id: int, claims: list[dict]) -> int:
    """Insert per-claim fact-check results for an article.

    Deletes existing claims first (idempotent re-check).
    Returns number of claims inserted.

    Args:
        article_id: The article ID to associate claims with.
        claims: List of dicts with keys: claim_text, verdict,
                evidence_summary, sources (list or JSON string).

    Returns:
        Number of claims inserted.
    """
    delete_claims_for_article(article_id)

    now = _utcnow()
    inserted = 0

    with SessionLocal() as session:
        for claim in claims:
            sources = claim.get("sources", [])
            if isinstance(sources, list):
                sources_json = json.dumps(sources)
            else:
                sources_json = sources

            claim_obj = Claim(
                article_id=article_id,
                claim_text=claim["claim_text"],
                verdict=claim["verdict"],
                evidence_summary=claim.get("evidence_summary"),
                sources=sources_json,
                created_at=now,
            )
            session.add(claim_obj)
            inserted += 1
        session.commit()

    return inserted


def get_claims_for_article(article_id: int) -> list[dict]:
    """Return all claims for an article, ordered by id.

    Args:
        article_id: The article ID to fetch claims for.

    Returns:
        List of dicts with keys: id, article_id, claim_text, verdict,
        evidence_summary, sources (parsed list), created_at.
    """
    with SessionLocal() as session:
        claims = (
            session.query(Claim)
            .filter(Claim.article_id == article_id)
            .order_by(Claim.id)
            .all()
        )

    result = []
    for claim in claims:
        sources_raw = claim.sources
        try:
            sources = json.loads(sources_raw) if sources_raw else []
        except (json.JSONDecodeError, TypeError):
            sources = []

        result.append(
            {
                "id": claim.id,
                "article_id": claim.article_id,
                "claim_text": claim.claim_text,
                "verdict": claim.verdict,
                "evidence_summary": claim.evidence_summary,
                "sources": sources,
                "created_at": claim.created_at,
            }
        )

    return result


def delete_claims_for_article(article_id: int) -> int:
    """Delete all claims for an article. Returns count deleted.

    Args:
        article_id: The article ID to delete claims for.

    Returns:
        Number of claims deleted.
    """
    with SessionLocal() as session:
        count = session.query(Claim).filter(Claim.article_id == article_id).count()

        session.query(Claim).filter(Claim.article_id == article_id).delete()
        session.commit()

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
