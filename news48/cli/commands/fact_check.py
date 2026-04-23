"""Fact-check command - fact-check articles."""

import asyncio

import typer

from news48.core.agents.fact_checker import run_cycle

from ._common import emit_json, status_msg


def fact_check(
    limit: int = typer.Option(10, "--limit", "-l", help="Maximum articles to check"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Fact-check articles that haven't been verified."""
    try:
        result = asyncio.run(run_cycle(limit=limit))
    except SystemExit:
        raise
    except Exception as e:
        status_msg(f"Error: {e}")
        return

    if output_json:
        emit_json(result)
    else:
        print(f"Fact-checked {result.get('checked', 0)} articles")
