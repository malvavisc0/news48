"""Agents command - manage autonomous agents."""

import asyncio

import typer

from agents.orchestrator import Orchestrator

from ._common import emit_error, emit_json

agents_app = typer.Typer(help="Manage autonomous agents.")

VALID_AGENTS = ["pipeline", "monitor", "reporter", "checker"]

DEFAULT_TASKS = {
    "pipeline": (
        "Run a full pipeline cycle: fetch all feeds to update article "
        "metadata, then for each feed domain check for empty articles "
        "and fork a download process per domain, then for each feed "
        "domain check for downloaded-but-unparsed articles and fork a "
        "parse process per domain, then purge expired articles."
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
) -> None:
    """Start the orchestrator daemon (continuous scheduling loop).

    Runs agents on their configured schedules, forking each as an
    independent subprocess. Press Ctrl+C to stop.
    """
    import logging

    from rich.console import Console
    from rich.table import Table

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = Console()
    orchestrator = Orchestrator()
    orchestrator.load_state()
    status = orchestrator.get_status()

    console.print()
    console.print(" news48 orchestrator", style="bold white")
    console.print("─" * 57, style="dim")
    console.print(f"  Tick interval: [cyan]{tick}s[/cyan]")
    console.print(
        "  Dashboard:     [dim]run [cyan]news48 agents dashboard[/cyan] "
        "in another terminal[/dim]"
    )
    console.print()

    table = Table(
        show_header=True, header_style="bold dim", border_style="dim"
    )
    table.add_column("Agent", style="bold", min_width=10)
    table.add_column("Interval", justify="right", min_width=10)
    table.add_column("Last Run", min_width=22)
    table.add_column("Status", min_width=10)

    for name, s in status.items():
        last = s.get("last_run") or "never"
        interval = f"{s['interval_minutes']}min"
        is_running = s.get("running", False)
        if is_running:
            status_str = "[green]running[/green]"
        elif last == "never":
            status_str = "[cyan]due[/cyan]"
        else:
            status_str = "[dim]waiting[/dim]"
        table.add_row(name, interval, last, status_str)

    console.print(table)
    console.print()

    orchestrator.start(tick_seconds=tick)


@agents_app.command(name="dashboard")
def agents_dashboard(
    tick: int = typer.Option(
        60,
        "--tick",
        "-t",
        help="Tick interval to display (cosmetic, matches orchestrator)",
    ),
    refresh: float = typer.Option(
        0.5,
        "--refresh",
        "-r",
        help="Dashboard refresh interval in seconds",
    ),
) -> None:
    """Live dashboard showing agent output (read-only).

    Connects to a running orchestrator by reading .orchestrator.json
    and tailing agent log files. Press Ctrl+C to exit.
    """
    import json
    import threading
    import time
    from pathlib import Path

    from rich.live import Live

    from agents.dashboard import Dashboard, EventBuffer, tail_file_stream

    STATE_FILE = Path(".orchestrator.json")

    dashboard = Dashboard(tick_seconds=tick)
    tailers: dict[str, tuple[threading.Thread, threading.Event]] = {}

    def sync_state() -> None:
        """Read .orchestrator.json and start/stop tailers as needed."""
        if not STATE_FILE.exists():
            return
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return

        current_running = data.get("running", {})

        # Start tailers for new agents
        for name, info in current_running.items():
            log_file = info.get("log_file", "")
            if name not in tailers and log_file:
                buffer = EventBuffer(max_lines=100)
                stop_event = threading.Event()
                thread = threading.Thread(
                    target=tail_file_stream,
                    args=(log_file, buffer, stop_event),
                    daemon=True,
                )
                thread.start()
                tailers[name] = (thread, stop_event)
                dashboard.buffers[name] = buffer
                dashboard.agent_status[name] = "running"

        # Mark completed agents
        for name in list(tailers.keys()):
            if name not in current_running:
                thread, stop_event = tailers.pop(name)
                stop_event.set()
                thread.join(timeout=2)
                dashboard.agent_status[name] = "completed"

    try:
        with Live(
            dashboard.render(),
            refresh_per_second=4,
            console=dashboard.console,
        ) as live:
            last_sync = 0.0
            while True:
                now = time.monotonic()
                if now - last_sync >= 3.0:
                    sync_state()
                    last_sync = now
                live.update(dashboard.render())
                time.sleep(refresh)
    except KeyboardInterrupt:
        # Stop all tailer threads
        for thread, stop_event in tailers.values():
            stop_event.set()
        for thread, stop_event in tailers.values():
            thread.join(timeout=2)
        dashboard.console.print("\n  [dim]Dashboard closed.[/dim]")


@agents_app.command(name="stop")
def agents_stop(
    agent: str = typer.Option(
        None, "--agent", "-a", help="Specific agent to stop"
    ),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Stop running agent(s)."""
    from rich.console import Console

    console = Console()
    orchestrator = Orchestrator()
    orchestrator.load_state()

    if agent:
        if agent not in VALID_AGENTS:
            emit_error(f"Unknown agent: {agent}", as_json=output_json)
            return
        result = orchestrator.stop_agent(agent)
    else:
        result = orchestrator.stop_all()

    if output_json:
        emit_json(result)
    else:
        stopped = result.get("stopped", [])
        already = result.get("already_stopped", [])
        if stopped:
            console.print(f"  Stopped: {', '.join(stopped)}", style="green")
        if already:
            console.print(f"  Not running: {', '.join(already)}", style="dim")


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
