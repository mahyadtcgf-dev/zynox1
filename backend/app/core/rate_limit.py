"""Rate limiting.

Authentication endpoints are throttled per-IP using an in-process token bucket.
The limiter is disabled entirely when RATE_LIMIT_ENABLED=false, which is what
the test suite uses.

Implemented as a FastAPI dependency rather than a decorator so it composes with
the existing `Depends` graph (`get_db`, `require_permission`) and needs no
wrapper around route functions.
"""

from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from fastapi import HTTPException, Request, status

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# ── Named limits ─────────────────────────────────────────────
# count / window_seconds. Tuned to stop bruteforce without tripping
# a legitimate user who retries after a typo.

LIMITS: dict[str, tuple[int, int]] = {
    "auth.login": (10, 60),
    "auth.refresh": (30, 60),
    "auth.change_password": (5, 60),
    "telegram.webapp_login": (10, 60),
}


class _Bucket:
    """Token bucket: refill is continuous, consumption is atomic."""

    __slots__ = ("tokens", "last")

    def __init__(self, capacity: float, now: float) -> None:
        self.tokens = capacity
        self.last = now

    def consume(self, capacity: float, refill_per_sec: float, now: float) -> bool:
        elapsed = max(0.0, now - self.last)
        self.tokens = min(capacity, self.tokens + elapsed * refill_per_sec)
        self.last = now
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False


class RateLimiter:
    """In-process rate limiter. Single process only — see ARCHITECTURE.md §12.

    Memory is bounded: each key holds one small bucket, and stale keys are
    swept on every check.
    """

    def __init__(self) -> None:
        self._buckets: dict[str, _Bucket] = defaultdict(lambda: _Bucket(0.0, 0.0))
        self._last_sweep = 0.0
        # Cap the key set so a hostile client cannot grow it unboundedly.
        self._max_keys = 10_000

    def check(self, name: str, key: str) -> None:
        """Raise 429 if `key` has exceeded the named limit."""
        if not settings.rate_limit_enabled:
            return

        try:
            capacity, window = LIMITS[name]
        except KeyError:
            # An unknown limit name is a programming error — fail loudly.
            raise RuntimeError(f"unknown rate limit: {name!r}") from None

        now = time.monotonic()

        # Sweep stale entries at most once per window.
        if now - self._last_sweep > window:
            stale = [
                k
                for k, bucket in self._buckets.items()
                if now - bucket.last > window * 2
            ]
            for k in stale:
                del self._buckets[k]
            self._last_sweep = now

        if len(self._buckets) > self._max_keys:
            self._buckets.clear()

        bucket = self._buckets[key]
        if not bucket.consume(float(capacity), capacity / window, now):
            logger.warning("rate limit exceeded", extra={"limit": name, "key": key})
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Try again later.",
                headers={"Retry-After": str(window)},
            )


_limiter = RateLimiter()


def _client_key(request: Request) -> str:
    """Best-effort client identifier.

    X-Forwarded-For is honoured (Railway terminates TLS on a proxy), falling
    back to the direct peer address.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def rate_limit(name: str) -> Callable[..., Any]:
    """FastAPI dependency: reject with 429 when the limit is exceeded.

    Usage:
        @router.post("/login", dependencies=[Depends(rate_limit("auth.login"))])
    """

    async def dependency(request: Request) -> None:
        _limiter.check(name, f"{name}:{_client_key(request)}")

    return dependency


__all__ = ["rate_limit", "LIMITS"]
