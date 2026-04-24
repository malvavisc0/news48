"""Fact-check command - fact-check articles."""

import asyncio

import typer

from news48.core.agents.fact_checker import run_cycle

from ._common import emit_error, emit_json, status_msg


def fact_check(
    limit: int = typer.Option(10, "--limit", "-l", help="Maximum articles to check"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Fact-check articles that haven't been verified.

    Runs the fact-checker agent cycle which claims eligible articles,
    searches for evidence via SearXNG, and records per-claim verdicts.

    Articles must be parsed first (via 'news48 parse') before they
    can be fact-checked.

    Examples:
        news48 fact-check
        news48 fact-check --limit 25 --json
    """
    try:
        result = asyncio.run(run_cycle(limit=limit))
    except SystemExit:
        raise
    except Exception as e:
        emit_error(str(e), as_json=output_json)

    if output_json:
        emit_json(result)
    else:
        print(f"Fact-checked {result.get('checked', 0)} articles")
