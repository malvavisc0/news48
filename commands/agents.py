"""Agents command - manage autonomous agents."""

import asyncio

import typer

from agents.orchestrator import Orchestrator

from ._common import emit_error, emit_json

agents_app = typer.Typer(help="Manage autonomous agents.")

VALID_AGENTS = ["pipeline", "monitor", "reporter", "checker"]

DEFAULT_TASKS = {
    "pipeline": (
        "Run a full pipeline cycle: fetch all feeds, download up to "
        "20 articles, parse up to 10 articles, then purge expired "
        "articles."
    ),
    "monitor": "Perform a full system health check and report any issues.",
    "reporter": "Generate a daily pipeline report.",
    "checker": (
        "Fact-check up to 5 recently parsed articles, focusing on "
        "politics, health, science, and conflict categories."
    ),
}

REPORT_TASKS = {
    "daily": "Generate a daily pipeline report.",
    "weekly": "Generate a weekly summary of system activity and "
    "performance.",
    "monthly": "Generate a monthly compliance and performance report.",
}


@agents_app.command(name="status")
def agents_status(
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show status of all agents (loads persisted state)."""
    orchestrator = Orchestrator()
    orchestrator.load_state()
    status = orchestrator.get_status()

    if output_json:
        emit_json(status)
    else:
        print("Agent Status")
        print("=" * 50)

        for agent_name, agent_status in status.items():
            print(f"\n{agent_name.upper()}")
            last = agent_status.get("last_run") or "Never"
            print(f"  Last run:    {last}")
            result = agent_status.get("last_result")
            if result:
                print(f"  Last result: {result}")
            error = agent_status.get("last_error")
            if error:
                print(f"  Last error:  {error[:80]}")
            print(
                f"  Enabled:     "
                f"{'Yes' if agent_status.get('enabled', True) else 'No'}"
            )
            print(
                f"  Interval:    "
                f"{agent_status.get('interval_minutes', 0)} minutes"
            )
            print(
                f"  Next run:    "
                f"{agent_status.get('next_run', 'immediate')}"
            )
            if agent_status.get("running"):
                info = agent_status["running_info"]
                print(
                    f"  RUNNING:     PID {info['pid']} "
                    f"since {info['started_at']}"
                )


@agents_app.command(name="run")
def agents_run(
    agent: str = typer.Option(
        None,
        "--agent",
        "-a",
        help="Specific agent to run (pipeline|monitor|reporter)",
    ),
    task: str = typer.Option(
        None,
        "--task",
        "-t",
        help="Custom task prompt for the agent",
    ),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Run agent(s) inline (one-shot mode)."""
    if agent:
        if agent not in VALID_AGENTS:
            emit_error(
                f"Unknown agent: {agent}. "
                f"Valid: {', '.join(VALID_AGENTS)}",
                as_json=output_json,
            )
            return

        task_prompt = task or DEFAULT_TASKS[agent]
        result = asyncio.run(_run_single_agent(agent, task_prompt))
    else:
        # Run all due agents (loads persisted state for scheduling)
        orchestrator = Orchestrator()
        orchestrator.load_state()
        result = asyncio.run(orchestrator.run_due_agents())

    if output_json:
        emit_json(result)
    else:
        agents_run_list = result.get("agents_run", [])
        agents_str = ", ".join(agents_run_list) if agents_run_list else "none"
        print(f"Agents run: {agents_str}")

        for agent_name in agents_run_list:
            agent_result = result["results"].get(agent_name, {})
            if agent_result.get("error"):
                print(f"\n{agent_name}: ERROR - " f"{agent_result['error']}")
            else:
                print(f"\n{agent_name}: completed")


async def _run_single_agent(agent_name: str, task: str) -> dict:
    """Run a single agent and return result dict."""
    orchestrator = Orchestrator()
    result = await orchestrator.run_agent(agent_name, task)
    return {
        "agents_run": [agent_name],
        "results": {agent_name: result},
    }


@agents_app.command(name="start")
def agents_start(
    tick: int = typer.Option(
        60,
        "--tick",
        "-t",
        help="Seconds between each scheduling tick (default: 60)",
    ),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Start the orchestrator daemon (continuous scheduling loop).

    Runs agents on their configured schedules, forking each as an
    independent subprocess. Press Ctrl+C to stop.
    """
    import logging

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    orchestrator = Orchestrator()
    orchestrator.load_state()

    if not output_json:
        status = orchestrator.get_status()
        print("Orchestrator starting")
        print(f"  Tick interval: {tick}s")
        print(f"  Agents: {', '.join(status.keys())}")
        for name, s in status.items():
            last = s.get("last_run") or "never"
            print(
                f"    {name}: every {s['interval_minutes']}min "
                f"(last: {last})"
            )
        print()

    orchestrator.start(tick_seconds=tick)


@agents_app.command(name="report")
def agents_report(
    report_type: str = typer.Option(
        "daily", "--type", "-t", help="Report type: daily|weekly|monthly"
    ),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Generate a report."""
    if report_type not in REPORT_TASKS:
        emit_error(
            f"Invalid report type: {report_type}. "
            f"Valid: {', '.join(REPORT_TASKS.keys())}",
            as_json=output_json,
        )
        return

    result = asyncio.run(
        _run_single_agent("reporter", REPORT_TASKS[report_type])
    )

    if output_json:
        emit_json(result)
    else:
        agent_result = result["results"].get("reporter", {})
        if agent_result.get("error"):
            print(f"Error: {agent_result['error']}")
        else:
            print(f"Report: {report_type}")
            print("=" * 50)
            print(agent_result.get("result", "No output"))
