"""Security and rate-limiting middleware for the web application."""

import time
from collections import defaultdict

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add standard security headers to all responses."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=()"
        )
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory rate limiter keyed by client IP.

    Limits:
    - General endpoints: 120 requests per minute
    - Search endpoint: 20 requests per minute

    Includes periodic sweep to remove stale IP entries and prevent
    unbounded memory growth under high-cardinality traffic.
    """

    _GENERAL_LIMIT = 120
    _SEARCH_LIMIT = 20
    _WINDOW = 60.0  # seconds
    _SWEEP_INTERVAL = 300.0  # full sweep every 5 minutes

    def __init__(self, app):
        super().__init__(app)
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._last_sweep: float = time.time()

    def _get_client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _cleanup(self, ip: str, now: float) -> None:
        cutoff = now - self._WINDOW
        self._requests[ip] = [t for t in self._requests[ip] if t > cutoff]

    def _maybe_sweep(self, now: float) -> None:
        """Remove empty IP entries to prevent unbounded dict growth."""
        if now - self._last_sweep < self._SWEEP_INTERVAL:
            return
        self._last_sweep = now
        empty_ips = [ip for ip, ts in self._requests.items() if not ts]
        for ip in empty_ips:
            del self._requests[ip]

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for static files and health check
        path = request.url.path
        if path.startswith("/static") or path == "/health":
            return await call_next(request)

        ip = self._get_client_ip(request)
        now = time.time()
        self._cleanup(ip, now)
        self._maybe_sweep(now)

        # Determine limit based on path
        if path.startswith("/search"):
            limit = self._SEARCH_LIMIT
        else:
            limit = self._GENERAL_LIMIT

        if len(self._requests[ip]) >= limit:
            return JSONResponse(
                {"detail": "Rate limit exceeded. Try again later."},
                status_code=429,
            )

        self._requests[ip].append(now)
        return await call_next(request)
