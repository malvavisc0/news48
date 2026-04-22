"""Dramatiq actor definitions with Periodiq periodic schedules.

All actors are defined here with their queue assignments, retry policies,
time limits, and cron schedules via Periodiq.

The broker module (agents.broker) must be imported before this module
so that the Redis broker is configured when actors are decorated.
"""

import asyncio
import logging
from typing import Any, cast

import dramatiq
from periodiq import cron

# Import broker first so Periodiq middleware is registered before any actor
# decorators are evaluated.
import agents.broker  # noqa: F401
from agents.workers import build_task_context

logger = logging.getLogger(__name__)

# Guard against re-registration on repeated imports.
# Use a module-level flag that persists across re-imports.
_broker = dramatiq.get_broker()


# Check if actors are already registered (handles re-imports)
def _actors_already_registered():
    if not _broker:
        return False
    return "sentinel_cycle" in _broker.actors


def _require_registered_actor(name: str) -> Any:
    actor = _broker.actors.get(name)
    if actor is None:
        raise RuntimeError(f"Registered actor missing from broker: {name}")
    return cast(Any, actor)


if not _actors_already_registered():
    # -----------------------------------------------------------------------
    # Sentinel Agent
    # -----------------------------------------------------------------------

    @dramatiq.actor(
        queue_name="sentinel",
        max_retries=1,
        time_limit=30 * 60 * 1000,  # 30 min in ms
    )
    def sentinel_cycle() -> Any:
        """Run one sentinel cycle as a Dramatiq actor."""
        from agents.sentinel import run

        task_context = build_task_context("sentinel")
        task_prompt = (
            "Run one sentinel cycle. Gather system health metrics, "
            "evaluate thresholds, create fix plans for detected issues, "
            "and delete feeds that are consistently problematic."
        )
        result = asyncio.run(run(task_prompt, task_context))
        return result

    @dramatiq.actor(
        queue_name="sentinel",
        periodic=cron("*/5 * * * *"),  # every 5 minutes
    )
    def scheduled_sentinel() -> None:
        """Periodic scheduler for sentinel — enqueues sentinel_cycle."""
        sentinel_cycle.send()

    # -----------------------------------------------------------------------
    # Executor Agent
    # -----------------------------------------------------------------------

    @dramatiq.actor(
        queue_name="executor",
        max_retries=1,
        time_limit=30 * 60 * 1000,  # 30 min in ms
    )
    def executor_cycle() -> Any:
        """Run one executor cycle as a Dramatiq actor."""
        from agents.executor import run
        from agents.tools.planner import peek_next_plan

        # Precondition check inside the actor
        family = peek_next_plan()
        if family is None:
            logger.debug("Executor: no claimable plans, skipping")
            return {"status": "skipped", "reason": "no_claimable_plans"}

        # Build the owner string from the Dramatiq message_id so that
        # PlanRecoveryMiddleware can release plans on actor failure.
        from dramatiq.middleware import CurrentMessage

        msg = CurrentMessage.get_current_message()
        owner_id = f"executor:dramatiq-{msg.message_id}" if msg else None
        owner_instruction = ""
        if owner_id:
            owner_instruction = (
                f" When calling claim_plan, pass "
                f"owner='{owner_id}' so the plan is linked to this actor."
            )

        task_context = build_task_context("executor")
        task_prompt = (
            "Run one execution cycle. Claim one eligible plan, execute its "
            "steps, verify the success conditions, and set the final plan "
            "status. Do not create plans."
            f"{owner_instruction}"
        )
        result = asyncio.run(run(task_prompt, task_context))
        return result

    @dramatiq.actor(
        queue_name="executor",
        periodic=cron("* * * * *"),  # every minute
    )
    def scheduled_executor() -> None:
        """Periodic scheduler for executor — enqueues executor_cycle."""
        executor_cycle.send()

    # -----------------------------------------------------------------------
    # Parser Agent
    # -----------------------------------------------------------------------

    @dramatiq.actor(
        queue_name="parser",
        max_retries=1,
        time_limit=30 * 60 * 1000,  # 30 min in ms
    )
    def parser_cycle() -> Any:
        """Run one autonomous parser cycle."""
        from agents.parser import run_autonomous

        result = asyncio.run(run_autonomous())
        return result

    @dramatiq.actor(
        queue_name="parser",
        max_retries=2,
        time_limit=10 * 60 * 1000,  # 10 min for single article
        min_backoff=30_000,  # 30s
        max_backoff=300_000,  # 5 min
    )
    def parse_single_article(
        article_id: int,
        title: str,
        content_file: str,
        url: str,
    ) -> Any:
        """Parse a single article.

        Can be enqueued directly for fine-grained control.
        """
        from agents.parser import run

        task = (
            f"\nParse the following article.\n"
            f"--------------------------------------\n"
            f"Article ID: {article_id}\n"
            f"Title: {title}\n"
            f"Content file path: {content_file}\n"
            f"URL: {url}\n"
            f"--------------------------------------\n"
        )
        result = asyncio.run(run(task, {}))
        return result

    @dramatiq.actor(
        queue_name="parser",
        periodic=cron("* * * * *"),  # every minute
    )
    def scheduled_parser() -> None:
        """Periodic scheduler for parser — enqueues parser_cycle."""
        parser_cycle.send()

    # -----------------------------------------------------------------------
    # Fact-Checker Agent
    # -----------------------------------------------------------------------

    @dramatiq.actor(
        queue_name="fact_checker",
        max_retries=1,
        time_limit=30 * 60 * 1000,  # 30 min in ms
    )
    def fact_check_cycle() -> Any:
        """Run one fact-check cycle."""
        from agents.fact_checker import run_cycle

        result = asyncio.run(run_cycle(limit=10))
        return result

    @dramatiq.actor(
        queue_name="fact_checker",
        periodic=cron("*/5 * * * *"),  # every 5 minutes
    )
    def scheduled_fact_checker() -> None:
        """Periodic scheduler for fact_checker."""
        fact_check_cycle.send()

    # -----------------------------------------------------------------------
    # Pipeline Actors
    # -----------------------------------------------------------------------

    @dramatiq.actor(
        queue_name="pipeline",
        max_retries=0,
        time_limit=10 * 60 * 1000,  # 10 min
    )
    def feed_fetch_cycle() -> Any:
        """Fetch all feeds once."""
        from database.feeds import get_all_feeds
        from helpers.feed import get_fetch_summary

        async def _run() -> Any:
            feeds = get_all_feeds()
            urls = [f["url"] for f in feeds]
            if not urls:
                return {"status": "no_feeds"}
            summary = await get_fetch_summary(urls, delay=0.0, track_db=True)
            return {
                "successful": len(summary.successful),
                "failed": len(summary.failed),
            }

        return asyncio.run(_run())

    @dramatiq.actor(
        queue_name="pipeline",
        max_retries=0,
        time_limit=10 * 60 * 1000,  # 10 min
    )
    def download_cycle() -> Any:
        """Download pending articles once."""
        from commands.download import _download

        result = asyncio.run(_download(limit=100, delay=0.0))
        return result

    @dramatiq.actor(
        queue_name="pipeline",
        periodic=cron("* * * * *"),  # every minute
    )
    def scheduled_feed_fetch() -> None:
        """Periodic scheduler for feed fetch."""
        feed_fetch_cycle.send()

    @dramatiq.actor(
        queue_name="pipeline",
        periodic=cron("* * * * *"),  # every minute
    )
    def scheduled_download() -> None:
        """Periodic scheduler for download."""
        download_cycle.send()

    # -----------------------------------------------------------------------
    # Plan Deadlock Healing
    # -----------------------------------------------------------------------

    @dramatiq.actor(
        queue_name="pipeline",
        max_retries=0,
        time_limit=5 * 60 * 1000,  # 5 min
        periodic=cron("* * * * *"),  # every minute
    )
    def heal_plan_deadlocks() -> Any:
        """Detect and repair campaign-parent deadlocks in pending plans."""
        import json

        from agents.tools.planner import (
            _auto_complete_campaigns,
            _ensure_plans_dir,
            _normalize_plan_for_consistency,
            _write_plan,
        )

        plans_dir = _ensure_plans_dir()
        healed = 0
        for plan_file in plans_dir.glob("*.json"):
            try:
                plan = json.loads(plan_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if _normalize_plan_for_consistency(plan):
                _write_plan(plan)
                healed += 1

        auto_completed = _auto_complete_campaigns(plans_dir)
        return {"healed": healed + auto_completed}

else:
    # Actors already registered — retrieve them from the broker
    sentinel_cycle = _require_registered_actor("sentinel_cycle")
    scheduled_sentinel = _require_registered_actor("scheduled_sentinel")
    executor_cycle = _require_registered_actor("executor_cycle")
    scheduled_executor = _require_registered_actor("scheduled_executor")
    parser_cycle = _require_registered_actor("parser_cycle")
    parse_single_article = _require_registered_actor("parse_single_article")
    scheduled_parser = _require_registered_actor("scheduled_parser")
    fact_check_cycle = _require_registered_actor("fact_check_cycle")
    scheduled_fact_checker = _require_registered_actor("scheduled_fact_checker")
    feed_fetch_cycle = _require_registered_actor("feed_fetch_cycle")
    download_cycle = _require_registered_actor("download_cycle")
    scheduled_feed_fetch = _require_registered_actor("scheduled_feed_fetch")
    scheduled_download = _require_registered_actor("scheduled_download")
    heal_plan_deadlocks = _require_registered_actor("heal_plan_deadlocks")
