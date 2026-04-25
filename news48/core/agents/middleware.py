"""Custom Dramatiq middleware classes.

Provides:
- StartupRecoveryMiddleware: Runs recovery tasks on worker boot.
- PlanRecoveryMiddleware: Releases plans claimed by failed actors.
- StructuredLoggingMiddleware: Logs actor lifecycle events.
"""

import logging
import time

import dramatiq

logger = logging.getLogger(__name__)


class StartupRecoveryMiddleware(dramatiq.Middleware):
    """Run recovery tasks when workers start.

    On every worker boot:
    - Recover stale executing plans
    - Release stale article claims
    - Archive terminal plans older than 24h
    - Clean archived plans older than 7 days
    - Clean expired byparr cache files
    """

    def after_worker_boot(self, broker, worker):
        """Called once when a worker process starts."""
        logger.info("StartupRecoveryMiddleware: running recovery tasks")
        try:
            import json

            from news48.core.database.articles import release_stale_article_claims

            from .tools.planner import (
                _archive_cleanup,
                archive_terminal_plans,
                recover_stale_plans,
            )

            # Recover stale plans
            payload = recover_stale_plans("Dramatiq worker startup recovery")
            result = json.loads(payload).get("result", {})
            logger.info(
                "Plan recovery: scanned=%s normalized=%s requeued=%s",
                result.get("scanned", 0),
                result.get("normalized", 0),
                result.get("requeued", 0),
            )

            # Release stale article claims
            article_result = release_stale_article_claims()
            if article_result.get("released"):
                logger.info(
                    "Article recovery: released %s stale claim(s)",
                    article_result["released"],
                )

            # Archive terminal plans older than 24h
            archive_result = archive_terminal_plans()
            if archive_result.get("archived"):
                logger.info(
                    "Plan archival: moved %s plan(s) to archive",
                    archive_result["archived"],
                )

            # Clean archived plans older than 7 days
            cleanup_result = _archive_cleanup()
            if cleanup_result.get("cleaned"):
                logger.info(
                    "Archive cleanup: deleted %s old plan(s)",
                    cleanup_result["cleaned"],
                )

            # Clean expired byparr cache files
            from news48.core.helpers.bypass import clean_expired_byparr_cache

            cache_result = clean_expired_byparr_cache()
            if cache_result.get("cleaned"):
                logger.info(
                    "Byparr cache cleanup: deleted %s expired file(s)",
                    cache_result["cleaned"],
                )
        except Exception as exc:
            logger.error("StartupRecoveryMiddleware failed: %s", exc)


class PlanRecoveryMiddleware(dramatiq.Middleware):
    """Release plans claimed by failed or timed-out actors.

    When an actor fails (exception, timeout, etc.), any plans it claimed
    are released back to pending so another worker can pick them up.
    """

    def after_process(self, broker, message, *, result=None, exception=None):
        """Called after an actor finishes processing a message."""
        if exception is not None:
            actor_name = message.actor_name
            message_id = message.message_id

            # Only handle executor-related actors
            if "executor" not in actor_name:
                return

            try:
                from .tools.planner import release_plans_for_owner

                owner = f"executor:dramatiq-{message_id}"
                released = release_plans_for_owner(owner)
                if released.get("count"):
                    logger.info(
                        "PlanRecoveryMiddleware: released %s plan(s) for %s",
                        released["count"],
                        owner,
                    )
            except Exception as exc:
                logger.error(
                    "PlanRecoveryMiddleware failed for %s: %s",
                    actor_name,
                    exc,
                )


class StructuredLoggingMiddleware(dramatiq.Middleware):
    """Log actor lifecycle events with structured data."""

    def before_process(self, broker, message):
        """Called before an actor processes a message."""
        message._start_time = time.monotonic()
        logger.info(
            "actor_started",
            extra={
                "actor": message.actor_name,
                "queue": message.queue_name,
                "message_id": message.message_id,
            },
        )

    def after_process(self, broker, message, *, result=None, exception=None):
        """Called after an actor finishes processing a message."""
        duration = time.monotonic() - getattr(message, "_start_time", 0)
        status = "error" if exception else "success"
        logger.info(
            f"actor_{status}",
            extra={
                "actor": message.actor_name,
                "queue": message.queue_name,
                "message_id": message.message_id,
                "duration_ms": round(duration * 1000, 2),
                "error": str(exception) if exception else None,
            },
        )
