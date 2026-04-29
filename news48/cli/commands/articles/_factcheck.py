"""Article fact-check CLI commands: check, claims."""

import json
import logging
import os

import typer

from news48.core.database import (
    claim_articles_for_processing,
    clear_article_processing_claim,
    compute_overall_verdict,
    get_article_by_id,
    get_article_by_url,
    get_claims_for_article,
    insert_claims,
    update_article_fact_check,
)

from .._common import emit_error, emit_json, require_db
from . import articles_app

logger = logging.getLogger(__name__)

# Hard limit on the number of claims per article.
_MAX_CLAIMS = 5


@articles_app.command(name="check")
def check_article(
    identifier: str = typer.Argument(..., help="Article ID or URL"),
    status: str = typer.Option(
        None,
        "--status",
        "-s",
        help="Fact-check verdict: verified|disputed|unverifiable|mixed",
    ),
    result: str = typer.Option(
        None,
        "--result",
        "-r",
        help="Free-text summary of the fact-check assessment",
    ),
    claims_json_file: str = typer.Option(
        None,
        "--claims-json-file",
        "-c",
        help="Path to a JSON file containing a claims array: "
        '[{"text", "verdict", "evidence", "sources"}]',
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Overwrite existing fact-check and override active claims",
    ),
    pending: bool = typer.Option(
        False,
        "--pending",
        help="Insert claims without setting fact_check_status "
        "(for placeholder claims before verification)",
    ),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Set the fact-check status and result for an article."""
    require_db()

    claims = None
    if claims_json_file:
        try:
            with open(claims_json_file, "r") as f:
                claims = json.load(f)
        except FileNotFoundError:
            emit_error(
                f"Claims file not found: {claims_json_file}",
                as_json=output_json,
            )
        except json.JSONDecodeError as e:
            emit_error(
                f"Invalid JSON in {claims_json_file}: {e}",
                as_json=output_json,
            )

    if status is None and claims is None and not pending:
        emit_error(
            "Must specify --status or --claims-json-file",
            as_json=output_json,
        )

    valid_statuses = {"verified", "disputed", "unverifiable", "mixed"}
    if status and status.lower() not in valid_statuses:
        emit_error(
            f"Invalid fact-check status '{status}'. "
            f"Valid: {', '.join(sorted(valid_statuses))}",
            as_json=output_json,
        )

    article = None
    try:
        article_id = int(identifier)
        article = get_article_by_id(article_id)
    except ValueError:
        article = get_article_by_url(identifier)

    if not article:
        emit_error(f"Article not found: {identifier}", as_json=output_json)

    if not article.get("parsed_at"):
        emit_error(
            f"Article {article['id']} has not been parsed yet. "
            "Parse it first before fact-checking.",
            as_json=output_json,
        )

    if article.get("fact_check_status") and not force and not pending:
        emit_error(
            f"Article {article['id']} is already fact-checked. "
            "Use --force to overwrite the existing result.",
            as_json=output_json,
        )

    claim_owner = f"fact_check:{os.getpid()}"
    claimed = claim_articles_for_processing(
        [article["id"]],
        "fact_check",
        claim_owner,
        force=force,
    )
    if article["id"] not in claimed:
        emit_error(
            f"Article {article['id']} is already being processed. "
            "Use --force to override the active claim.",
            as_json=output_json,
        )

    if claims is not None:
        normalized_claims = []
        article_url = article.get("url", "")
        for c in claims:
            sources = c.get("sources", [])
            # Filter out the article's own URL from sources
            # to prevent circular verification.
            if article_url and article_url in sources:
                sources = [s for s in sources if s != article_url]
                logger.warning(
                    "Filtered article's own URL from claim " "sources for article %s",
                    article["id"],
                )
            # Accept multiple key names for claim text — LLMs
            # may use "text", "claim_text", "claim", or "statement".
            claim_text = (
                c.get("claim_text")
                or c.get("text")
                or c.get("claim")
                or c.get("statement")
                or ""
            )
            normalized = {
                "claim_text": claim_text,
                "verdict": c.get("verdict", "unverifiable"),
                "evidence_summary": c.get("evidence_summary", c.get("evidence", "")),
                "sources": sources,
            }
            normalized_claims.append(normalized)

        # Filter out claims with empty text.
        normalized_claims = [c for c in normalized_claims if c["claim_text"].strip()]
        if not normalized_claims:
            clear_article_processing_claim(article["id"], owner=claim_owner)
            emit_error(
                "No valid claims — all had empty text.",
                as_json=output_json,
            )

        # Enforce hard claim limit.
        if len(normalized_claims) > _MAX_CLAIMS:
            logger.warning(
                "Claims count (%d) exceeds limit (%d) for "
                "article %s — truncating to first %d claims.",
                len(normalized_claims),
                _MAX_CLAIMS,
                article["id"],
                _MAX_CLAIMS,
            )
            normalized_claims = normalized_claims[:_MAX_CLAIMS]

        insert_claims(article["id"], normalized_claims)

        if pending:
            # --pending: insert claims only, do not set
            # fact_check_status. Used for placeholder claims
            # before evidence search.
            clear_article_processing_claim(article["id"], owner=claim_owner)
            data = {
                "checked": True,
                "id": article["id"],
                "url": article["url"],
                "title": article["title"],
                "fact_check_status": article.get("fact_check_status"),
                "claims_count": len(normalized_claims),
                "pending": True,
            }
            if output_json:
                emit_json(data)
            else:
                title = article["title"] or "Untitled"
                print(f"Saved {len(normalized_claims)} claims (pending)")
                print(f"  Article: {title} (ID: {article['id']})")
            return

        final_status = (
            status.lower() if status else compute_overall_verdict(normalized_claims)
        )
    else:
        final_status = status.lower()

    try:
        updated = update_article_fact_check(
            article["id"],
            status=final_status,
            result=result,
            force=force,
        )
    finally:
        clear_article_processing_claim(article["id"], owner=claim_owner)

    if not updated:
        emit_error(
            f"Article {article['id']} could not be updated. "
            "It may already have a fact-check result.",
            as_json=output_json,
        )

    data = {
        "checked": updated,
        "id": article["id"],
        "url": article["url"],
        "title": article["title"],
        "fact_check_status": final_status,
        "fact_check_result": result,
        "claims_count": len(claims) if claims else 0,
    }

    if output_json:
        emit_json(data)
    else:
        title = article["title"] or "Untitled"
        if updated:
            print(f"Fact-checked article: {title}")
            print(f"  ID: {article['id']}")
            print(f"  Status: {final_status}")
            if result:
                print(f"  Result: {result}")
        else:
            print(f"Error: Failed to update article {article['id']}")


@articles_app.command(name="claims")
def article_claims(
    identifier: str = typer.Argument(..., help="Article ID or URL"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show per-claim fact-check results for an article."""
    require_db()

    article = None
    try:
        article_id = int(identifier)
        article = get_article_by_id(article_id)
    except ValueError:
        article = get_article_by_url(identifier)

    if not article:
        emit_error(f"Article not found: {identifier}", as_json=output_json)

    claims = get_claims_for_article(article["id"])

    verdict_counts = {}
    for c in claims:
        v = c["verdict"]
        verdict_counts[v] = verdict_counts.get(v, 0) + 1

    data = {
        "id": article["id"],
        "url": article["url"],
        "title": article["title"],
        "total_claims": len(claims),
        "verdict_counts": verdict_counts,
        "claims": claims,
    }

    if output_json:
        emit_json(data)
    else:
        title = article["title"] or "Untitled"
        print(f"Claims for: {title}")
        print(f"  ID: {article['id']}")
        print(f"  Total claims: {len(claims)}")
        if verdict_counts:
            counts = ", ".join(f"{v}: {c}" for v, c in sorted(verdict_counts.items()))
            print(f"  Verdicts: {counts}")
        print()
        for c in claims:
            print(f"  [{c['verdict']}] {c['claim_text']}")
            if c.get("evidence_summary"):
                print(f"    Evidence: {c['evidence_summary']}")
            if c.get("sources"):
                srcs = ", ".join(c["sources"])
                print(f"    Sources: {srcs}")
