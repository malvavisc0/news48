"""Dramatiq broker configuration — imported before actors.

Sets up the Redis broker and registers custom middleware.
This module must be imported before any actor definitions
so that the broker is configured when actors are decorated.

Safe for repeated imports — only configures once.
"""

import dramatiq
from dramatiq.brokers.redis import RedisBroker
from periodiq import PeriodiqMiddleware

from config import Redis

# Dramatiq may lazily create a default broker before this module is imported.
# Always replace it with the project-configured Redis broker so actor options
# from our middleware (including Periodiq's `periodic`) are available before
# any actor decorators run.
existing_broker = dramatiq.get_broker()
if (
    isinstance(existing_broker, RedisBroker)
    and getattr(existing_broker, "url", None) == Redis.url
):
    redis_broker = existing_broker
else:
    redis_broker = RedisBroker(url=Redis.url)
    dramatiq.set_broker(redis_broker)

# Register custom middleware (must be added AFTER set_broker)
# Import here to avoid circular imports — actors import broker at top.
from agents.middleware import PlanRecoveryMiddleware  # noqa: E402
from agents.middleware import (
    StartupRecoveryMiddleware,  # noqa: E402
    StructuredLoggingMiddleware,
)

# Only add middleware once (check by class name)
_middleware_names = {type(m).__name__ for m in redis_broker.middleware}
for mw_class in [
    PeriodiqMiddleware,
    StartupRecoveryMiddleware,
    PlanRecoveryMiddleware,
    StructuredLoggingMiddleware,
]:
    if mw_class.__name__ not in _middleware_names:
        redis_broker.add_middleware(mw_class())
