"""Article processing claim management."""

from sqlalchemy import or_

from ..connection import SessionLocal, _utcnow
from ..models import Article
from ._constants import _CLAIM_TIMEOUT_MINUTES, _VALID_PROCESSING_ACTIONS, _claim_cutoff


def claim_articles_for_processing(
    article_ids: list[int],
    action: str,
    owner: str,
    *,
    force: bool = False,
    stale_after_minutes: int = _CLAIM_TIMEOUT_MINUTES,
) -> list[int]:
    """Claim articles for a processing action."""
    if not article_ids:
        return []
    if action not in _VALID_PROCESSING_ACTIONS:
        raise ValueError(
            f"Invalid processing action '{action}'. "
            f"Valid: {', '.join(sorted(_VALID_PROCESSING_ACTIONS))}"
        )

    now = _utcnow()
    cutoff = _claim_cutoff(stale_after_minutes)

    with SessionLocal() as session:
        query = session.query(Article).filter(Article.id.in_(article_ids))
        if not force:
            query = query.filter(
                or_(
                    Article.processing_status.is_(None),
                    Article.processing_started_at.is_(None),
                    Article.processing_started_at < cutoff,
                    Article.processing_owner == owner,
                )
            )

        articles = query.with_for_update().all()
        for article in articles:
            article.processing_status = action
            article.processing_owner = owner
            article.processing_started_at = now
        session.commit()

        # Re-query to get the actually claimed IDs
        claimed = (
            session.query(Article.id)
            .filter(
                Article.id.in_(article_ids),
                Article.processing_status == action,
                Article.processing_owner == owner,
            )
            .all()
        )
        return [int(row[0]) for row in claimed]


def clear_article_processing_claim(
    article_id: int,
    owner: str | None = None,
) -> None:
    """Clear the processing claim for an article."""
    with SessionLocal() as session:
        article = session.get(Article, article_id)
        if article:
            if owner is None or article.processing_owner == owner:
                article.processing_status = None
                article.processing_owner = None
                article.processing_started_at = None
                session.commit()


def release_stale_article_claims(
    stale_after_minutes: int = _CLAIM_TIMEOUT_MINUTES,
) -> dict:
    """Release processing claims for articles stuck after a crash."""
    cutoff = _claim_cutoff(stale_after_minutes)

    with SessionLocal() as session:
        stale_query = session.query(Article).filter(
            Article.processing_status.in_(_VALID_PROCESSING_ACTIONS),
            Article.processing_started_at.is_not(None),
            Article.processing_started_at < cutoff,
        )

        count = stale_query.count()

        stale_query.update(
            {
                Article.processing_status: None,
                Article.processing_owner: None,
                Article.processing_started_at: None,
            },
            synchronize_session=False,
        )
        session.commit()

    return {"released": count or 0}
