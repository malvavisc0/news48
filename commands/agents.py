"""Agents command - manage autonomous agents.

After the Dramatiq migration, agents are run via:
- `periodiq agents.actors` — scheduler that enqueues tasks on cron
- `dramatiq agents.actors` — worker that executes tasks from queues

This module provides CLI commands for manual interaction:
- `agents run` — enqueue a one-shot agent task to Dramatiq (or run inline)
- `agents status` — show Redis queue depths and Periodiq schedule info
"""

import asyncio
import json

import typer

from ._common import emit_error, emit_json

agents_app = typer.Typer(help="Manage autonomous agents.")

VALID_AGENTS = ["sentinel", "executor", "parser", "fact_checker"]

DEFAULT_TASKS = {
    "sentinel": (
        "Run one sentinel cycle. Gather system health metrics, "
        "evaluate thresholds, create fix plans for detected issues, "
        "and delete feeds that are consistently problematic."
    ),
    "executor": (
        "Run one execution cycle. Claim one eligible plan, execute its "
        "steps, verify the success conditions, and set the final plan "
        "status. Do not create plans."
    ),
    "parser": (
        "Run one parser cycle. Claim eligible downloaded articles from "
        "the database, parse one claimed article at a time, update the "
        "article, and release the claim when finished."
    ),
    "fact_checker": (
        "Run one fact-check cycle. Claim eligible fact-unchecked "
        "articles, search for evidence, and record verdicts."
    ),
}

# Periodiq cron schedules from agents.actors
CRON_SCHEDULES = {
    "sentinel": "*/5 * * * *",
    "executor": "* * * * *",
    "parser": "* * * * *",
    "fact_checker": "*/5 * * * *",
}

QUEUE_NAMES = {
    "sentinel": "sentinel",
    "executor": "executor",
    "parser": "parser",
    "fact_checker": "fact_checker",
}


def _get_redis_connection():
    """Get a Redis connection, or return None if unavailable."""
    try:
        import redis

        from config import Redis

        return redis.from_url(Redis.url)
    except Exception:
        return None


@agents_app.command(name="status")
def agents_status(
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show status of all agents (Redis queue depths + cron schedules)."""
    r = _get_redis_connection()

    status_data = {}
    for agent_name in VALID_AGENTS:
        queue_name = QUEUE_NAMES[agent_name]
        queue_depth = 0
        if r:
            try:
                queue_depth = r.llen(f"dramatiq:{queue_name}")
            except Exception:
                queue_depth = -1  # indicates Redis unavailable

        status_data[agent_name] = {
            "queue": queue_name,
            "queue_depth": queue_depth,
            "cron_schedule": CRON_SCHEDULES[agent_name],
        }

    if output_json:
        emit_json(status_data)
    else:
        print("Agent Status")
        print("=" * 50)

        for agent_name, info in status_data.items():
            print(f"\n{agent_name.upper()}")
            print(f"  Queue:       {info['queue']}")
            depth = info["queue_depth"]
            if depth < 0:
                print("  Queue depth: (Redis unavailable)")
            else:
                print(f"  Queue depth: {depth}")
            print(f"  Cron:        {info['cron_schedule']}")


@agents_app.command(name="run")
def agents_run(
    agent: str = typer.Option(
        None,
        "--agent",
        "-a",
        help="Specific agent to run (sentinel|executor|parser|fact_checker)",
    ),
    task: str = typer.Option(
        None,
        "--task",
        "-t",
        help="Custom task prompt for the agent",
    ),
    inline: bool = typer.Option(
        False,
        "--inline",
        help="Run agent inline (no Redis/Dramatiq needed, for debugging)",
    ),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Run agent(s).

    Enqueue to Dramatiq by default, or run inline with --inline.
    """
    if agent:
        if agent not in VALID_AGENTS:
            emit_error(
                f"Unknown agent: {agent}. " f"Valid: {', '.join(VALID_AGENTS)}",
                as_json=output_json,
            )
            return

        task_prompt = task or DEFAULT_TASKS[agent]

        if inline:
            # Run inline for debugging without Docker/Redis
            asyncio.run(_run_single_agent_inline(agent, task_prompt))
        else:
            # Enqueue to Dramatiq
            _enqueue_agent(agent, task_prompt)
    else:
        # Run all agents — enqueue each to Dramatiq
        for agent_name in VALID_AGENTS:
            task_prompt = DEFAULT_TASKS[agent_name]
            _enqueue_agent(agent_name, task_prompt)


def _enqueue_agent(agent_name: str, task_prompt: str) -> None:
    """Enqueue an agent task to Dramatiq."""
    try:
        import agents.broker  # noqa: F401
        from agents.actors import (
            executor_cycle,
            fact_check_cycle,
            parser_cycle,
            sentinel_cycle,
        )

        actor_map = {
            "sentinel": sentinel_cycle,
            "executor": executor_cycle,
            "parser": parser_cycle,
            "fact_checker": fact_check_cycle,
        }

        actor = actor_map.get(agent_name)
        if actor:
            msg = actor.send()
            print(f"  Enqueued {agent_name} task (message_id={msg.message_id})")
        else:
            emit_error(f"No Dramatiq actor for agent: {agent_name}")
    except Exception as exc:
        emit_error(f"Failed to enqueue {agent_name}: {exc}")


async def _run_single_agent_inline(agent_name: str, task: str):
    """Run a single agent inline (for debugging without Dramatiq)."""
    from agents.workers import build_task_context

    task_context = build_task_context(agent_name)

    if agent_name == "sentinel":
        from agents.sentinel import run

        result = await run(task, task_context)
    elif agent_name == "executor":
        from agents.executor import run

        result = await run(task, task_context)
    elif agent_name == "parser":
        from agents.parser import run_autonomous

        result = await run_autonomous()
    elif agent_name == "fact_checker":
        from agents.fact_checker import run_cycle

        result = await run_cycle(limit=10)
    else:
        emit_error(f"Unknown agent: {agent_name}")
        return

    print(f"  {agent_name} completed: {json.dumps(result, default=str)[:200]}")
