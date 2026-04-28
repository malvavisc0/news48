"""Fact-check commands - run and status."""

import asyncio

import typer

from news48.core.agents.fact_checker import run_cycle
from news48.core.database import get_articles_paginated

from ._common import emit_json, require_db

fact_check_app = typer.Typer(help="Fact-check articles and view status.")


@fact_check_app.command(name="run")
def fact_check_run(
    limit: int = typer.Option(
        10, "--limit", "-l", help="Maximum articles to check"
    ),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Fact-check articles that haven't been verified.

    Runs the fact-checker agent cycle which claims eligible articles,
    searches for evidence via SearXNG, and records per-claim verdicts.

    Examples:
        news48 fact-check run
        news48 fact-check run --limit 25 --json
    """
    try:
        result = asyncio.run(run_cycle(limit=limit))
    except SystemExit:
        raise
    except Exception as e:
        from ._common import emit_error

        emit_error(str(e), as_json=output_json)

    if output_json:
        emit_json(result)
    else:
        print(f"Fact-checked {result.get('checked', 0)} articles")


@fact_check_app.command(name="status")
def fact_check_status(
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show fact-check pipeline status.

    Displays counts of articles by fact-check status, active processing,
    and recent fact-check plans.

    Examples:
        news48 fact-check status
        news48 fact-check status --json
    """
    require_db()

    unchecked, unchecked_total = get_articles_paginated(
        limit=1, status="fact-unchecked"
    )
    checked, checked_total = get_articles_paginated(
        limit=1, status="fact-checked"
    )
    errors, errors_total = get_articles_paginated(
        limit=1, status="fact-check-error"
    )

    # Per-verdict breakdown (only for actual verdicts, not errors)
    from news48.core.database.connection import SessionLocal
    from news48.core.database.models import Article

    verdict_counts: dict[str, int] = {}
    with SessionLocal() as session:
        for verdict in ("verified", "disputed", "mixed", "unverifiable"):
            cnt = (
                session.query(Article)
                .filter(Article.fact_check_status == verdict)
                .count()
            )
            verdict_counts[verdict] = cnt

        # Count actively processing articles
        processing = (
            session.query(Article)
            .filter(
                Article.processing_status == "fact_check",
            )
            .count()
        )

    # Count fact-check plans
    from news48.core.agents.tools.planner._db import db_iter_plans

    plans = {"pending": 0, "executing": 0, "completed": 0, "failed": 0}
    for plan in db_iter_plans():
        if plan.get("scope_type") != "fact_check":
            continue
        plan_status = plan.get("status", "")
        if plan_status in plans:
            plans[plan_status] += 1

    data = {
        "articles": {
            "fact_unchecked": unchecked_total,
            "fact_checked": checked_total,
            "fact_check_error": errors_total,
            "currently_processing": processing,
            "verdicts": verdict_counts,
        },
        "plans": plans,
    }

    if output_json:
        emit_json(data)
    else:
        print("Fact-Check Status")
        print("=" * 40)
        print(f"  Waiting to check:    {unchecked_total}")
        print(f"  Checked (verdicts):  {checked_total}")
        print(f"    ✓ Verified:        {verdict_counts['verified']}")
        print(f"    ✗ Disputed:        {verdict_counts['disputed']}")
        print(f"    ~ Mixed:           {verdict_counts['mixed']}")
        print(f"    ? Unverifiable:    {verdict_counts['unverifiable']}")
        print(f"  Errors (retryable):  {errors_total}")
        print(f"  Currently processing: {processing}")
        print()
        print("Plans")
        print("-" * 40)
        print(f"  Pending:    {plans['pending']}")
        print(f"  Executing:  {plans['executing']}")
        print(f"  Completed:  {plans['completed']}")
        print(f"  Failed:     {plans['failed']}")
