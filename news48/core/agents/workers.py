"""Shared helper functions for Dramatiq actors.

Provides task context building and other utilities used across actors.
"""

import logging
import os
from typing import Any, Dict

logger = logging.getLogger(__name__)


def build_task_context(name: str) -> Dict[str, Any]:
    """Build the task_context dict for a given agent.

    Mirrors Orchestrator._build_task_context() but is called
    inside the actor at execution time rather than before fork.

    Args:
        name: Agent name (sentinel, executor, parser, fact_checker).

    Returns:
        Dict with context data for the agent.
    """
    task_context: Dict[str, Any] = {}

    if name == "executor":
        try:
            from .tools.planner import peek_next_plan

            family = peek_next_plan()
            if family:
                task_context["plan_family"] = family
        except Exception as exc:
            logger.warning("Failed to peek next plan family: %s", exc)

    elif name == "sentinel":
        try:
            email_ready = bool(
                os.getenv("SMTP_HOST", "")
                and os.getenv("SMTP_USER", "")
                and os.getenv("SMTP_PASS", "")
                and os.getenv("MONITOR_EMAIL_TO", "")
            )
            task_context["email_configured"] = email_ready

            # Add backlog context for conditional skills
            from news48.core.database import get_article_stats

            article_stats = get_article_stats()
            task_context["backlog_high"] = bool(
                max(
                    int(article_stats.get("download_backlog") or 0),
                    int(article_stats.get("parse_backlog") or 0),
                )
                > 200
            )
        except Exception as exc:
            logger.warning("Failed to build sentinel task context: %s", exc)

    elif name == "fact_checker":
        # Fact-checker uses default skills; no special context needed.
        pass

    return task_context
