"""Agents command - manage autonomous agents."""

import asyncio
from typing import Literal

import typer

from agents.orchestrator import Orchestrator
from agents.schedules import DEFAULT_SCHEDULES

from ._common import emit_error, emit_json

agents_app = typer.Typer(help="Manage autonomous agents.")

VALID_AGENTS = ["planner", "executor", "parser", "monitor"]

DEFAULT_TASKS = {
    name: schedule.task_prompt for name, schedule in DEFAULT_SCHEDULES.items()
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
                f"  Interval:    " f"{agent_status.get('interval_minutes', 0)} minutes"
            )
            print(f"  Next run:    " f"{agent_status.get('next_run', 'immediate')}")
            max_c = agent_status.get("max_concurrent", 1)
            if max_c > 1:
                print(f"  Concurrency: {max_c}")
            if agent_status.get("running"):
                count = agent_status.get("running_count", 0)
                infos = agent_status.get("running_info", [])
                label = f"{count} instance{'s' if count != 1 else ''}"
                print(f"  RUNNING:     {label}")
                for info in infos:
                    print(f"    PID {info['pid']} " f"since {info['started_at']}")


@agents_app.command(name="run")
def agents_run(
    agent: Literal["planner", "executor", "parser", "monitor"] = (
        typer.Option(
            None,
            "--agent",
            "-a",
            help="Specific agent to run (planner|executor|parser|monitor)",
        )
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
                f"Unknown agent: {agent}. " f"Valid: {', '.join(VALID_AGENTS)}",
                as_json=output_json,
            )
            return

        task_prompt = task or DEFAULT_TASKS[agent]
        asyncio.run(_run_single_agent(agent, task_prompt))
    else:
        # Run all due agents (loads persisted state for scheduling)
        orchestrator = Orchestrator()
        orchestrator.load_state()
        asyncio.run(orchestrator.run_due_agents())


async def _run_single_agent(
    agent_name: Literal["planner", "executor", "parser", "monitor"],
    task: str,
):
    """Run a single agent."""
    await Orchestrator().run_agent(agent_name, task)


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

    table = Table(show_header=True, header_style="bold dim", border_style="dim")
    table.add_column("Agent", style="bold", min_width=10)
    table.add_column("Interval", justify="right", min_width=10)
    table.add_column("Slots", justify="right", min_width=6)
    table.add_column("Last Run", min_width=22)
    table.add_column("Status", min_width=10)

    for name, s in status.items():
        last = s.get("last_run") or "never"
        interval = f"{s['interval_minutes']}min"
        max_c = s.get("max_concurrent", 1)
        slots = str(max_c) if max_c > 1 else ""
        is_running = s.get("running", False)
        running_count = s.get("running_count", 0)
        if is_running:
            if running_count > 1:
                status_str = f"[green]running ({running_count})[/green]"
            else:
                status_str = "[green]running[/green]"
        elif last == "never":
            status_str = "[cyan]due[/cyan]"
        else:
            status_str = "[dim]waiting[/dim]"
        table.add_row(name, interval, slots, last, status_str)

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

    Fixed 4-panel layout: planner, executor, monitor, stats.
    Connects to a running orchestrator by reading .orchestrator.json
    and tailing agent log files. Press Ctrl+C to exit.
    """
    import json
    import threading
    import time
    from pathlib import Path

    from rich.live import Live

    from agents.dashboard import (
        Dashboard,
        EventBuffer,
        _get_article_stats,
        tail_file_stream,
    )

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

        # Collect all active tailer keys from current state
        active_tailer_keys: set[str] = set()

        # Start tailers for new agent instances
        for name, run_data in current_running.items():
            # Support both list (current) and dict (legacy) formats
            instances = run_data if isinstance(run_data, list) else [run_data]
            for i, info in enumerate(instances):
                pid = info.get("pid")
                if pid:
                    tailer_key = f"{name}:{pid}"
                elif len(instances) > 1:
                    # Fallback for malformed legacy entries without pid
                    tailer_key = f"{name}:{i}"
                else:
                    tailer_key = name
                active_tailer_keys.add(tailer_key)
                log_file = info.get("log_file", "")
                if tailer_key not in tailers and log_file:
                    # Keep per-instance buffer keyed by tailer_key
                    if tailer_key not in dashboard.buffers:
                        dashboard.buffers[tailer_key] = EventBuffer(max_lines=100)
                    buffer = dashboard.buffers[tailer_key]
                    stop_event = threading.Event()
                    thread = threading.Thread(
                        target=tail_file_stream,
                        args=(log_file, buffer, stop_event),
                        daemon=True,
                    )
                    thread.start()
                    tailers[tailer_key] = (thread, stop_event)
                    dashboard.agent_status[name] = "running"

        # Mark completed agents
        for tailer_key in list(tailers.keys()):
            if tailer_key not in active_tailer_keys:
                thread, stop_event = tailers.pop(tailer_key)
                stop_event.set()
                thread.join(timeout=2)
                # Extract agent name from tailer_key
                agent_name = tailer_key.split(":")[0]
                # Only mark completed if no other instances running
                if not any(
                    k.startswith(agent_name + ":") or k == agent_name
                    for k in active_tailer_keys
                ):
                    dashboard.agent_status[agent_name] = "completed"

        # Refresh article stats
        dashboard.stats_data = _get_article_stats()

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
        dashboard.console.print("\n  [dim]Dashboard closed.[/dim]")
    finally:
        # Stop all tailer threads (handles any exception, not just Ctrl+C)
        for thread, stop_event in tailers.values():
            stop_event.set()
        for thread, stop_event in tailers.values():
            thread.join(timeout=2)


@agents_app.command(name="stop")
def agents_stop(
    agent: str = typer.Option(None, "--agent", "-a", help="Specific agent to stop"),
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
