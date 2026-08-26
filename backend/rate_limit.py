"""Per-client rate limiting for the public API.

``POST /api/itinerary`` is unauthenticated and **expensive to serve**: every
request is a real MILP solve, up to ``SOLVER_TIME_LIMIT_S`` of CPU on an
instance that owns ~0.1 of a core. Requests therefore queue rather than
overlap, so a short loop — or a crawler, or one impatient visitor — makes the
app unresponsive for everyone else. No attack is required, only impoliteness.

The defence works because the two paths cost wildly different amounts:
**rejecting takes about a millisecond, serving takes seconds.** Enforcing the
limit as a dependency means the solver is never reached by a request that is
over the line.

Deliberately hand-rolled rather than pulling in a library: one process, one
route, no Redis. A dict of client → recent request times plus a lock is the
whole mechanism. The thing to revisit first, if this app ever runs more than
one process, is that these counters are per-process and stop being shared.
"""

from __future__ import annotations

import math
import os
import threading
import time
from collections import deque

from fastapi import HTTPException, Request

# Requests allowed per client per window. Generous for a person — planning a
# route means reading the result before asking again — and fatal to a loop.
RATE_LIMIT_PER_MINUTE = int(os.environ.get("RATE_LIMIT_PER_MINUTE", "10"))

WINDOW_S = 60.0

# How many checks pass between sweeps of the whole table. Sweeping on every
# call would make each request O(clients); never sweeping would leak one entry
# per distinct client forever.
_SWEEP_EVERY = 1000


def client_ip(request: Request) -> str:
    """Identify the caller, for use as a rate-limiting key.

    Args:
        request: the incoming request.

    Returns:
        The client's address, or ``"unknown"`` if it cannot be determined.

    Behind a proxy — which is exactly how this app is deployed — every request
    arrives carrying the *proxy's* address in ``request.client.host``. Keying
    on that would put every visitor on Earth in a single bucket, so the first
    person to hit the limit would lock out everybody. The forwarding chain in
    ``X-Forwarded-For`` holds the real one.

    Takes the **rightmost** entry, which is the security-critical part. A
    client may send its own ``X-Forwarded-For`` header, and a proxy *appends*
    to that header rather than replacing it::

        X-Forwarded-For: 1.2.3.4, 203.0.113.9
                         ^ sent by the client    ^ appended by our proxy
                         (forgeable)             (trustworthy)

    Reading the leftmost value — the common tutorial advice — would let anyone
    bypass the limit entirely by inventing a new address per request. The
    rightmost entry is the one our own proxy wrote.

    Assumes exactly one trusted proxy in front of the app. Adding another (a
    CDN ahead of the host, say) would mean counting back one more hop.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
        if hops:
            return hops[-1]
    return request.client.host if request.client else "unknown"


class SlidingWindowLimiter:
    """Allow at most ``limit`` requests per ``window_s``, per key, in memory.

    Each key keeps the timestamps of its recent requests; they fall off the
    front as they age out. A *fixed* window would be simpler but lets a client
    send 2x the limit across a boundary — the whole allowance at 11:59:59 and
    the whole allowance again at 12:00:00. A sliding window cannot be gamed
    that way.
    """

    def __init__(self, *, limit: int, window_s: float = WINDOW_S) -> None:
        """Build a limiter.

        Args:
            limit: requests allowed per window, per key.
            window_s: length of the window in seconds.
        """
        self._limit = limit
        self._window_s = window_s
        self._hits: dict[str, deque[float]] = {}
        # The route handler is a plain ``def``, so FastAPI runs it in a worker
        # threadpool and several threads reach this table at once. Without the
        # lock, two threads can both read a count of 9 and both append, and
        # the limit quietly leaks.
        self._lock = threading.Lock()
        self._checks_since_sweep = 0

    def check(self, key: str) -> float | None:
        """Record a request for ``key`` and say whether it is allowed.

        Args:
            key: the caller's identity (see :func:`client_ip`).

        Returns:
            ``None`` when the request is allowed, otherwise the number of
            seconds until the caller may try again.

        A rejected request is deliberately **not** recorded. Counting refusals
        would let a client that keeps hammering extend its own lockout without
        limit, which punishes a retry loop far more than intended.
        """
        # Monotonic, not wall-clock: immune to the clock being adjusted
        # underneath us, which would otherwise widen or collapse the window.
        now = time.monotonic()

        with self._lock:
            self._checks_since_sweep += 1
            if self._checks_since_sweep >= _SWEEP_EVERY:
                self._sweep(now)

            hits = self._hits.setdefault(key, deque())
            cutoff = now - self._window_s
            while hits and hits[0] <= cutoff:
                hits.popleft()

            if len(hits) >= self._limit:
                # Room appears when the oldest recorded hit ages out.
                return hits[0] + self._window_s - now

            hits.append(now)
            return None

    def clear(self) -> None:
        """Forget every recorded request. Used to isolate tests."""
        with self._lock:
            self._hits.clear()
            self._checks_since_sweep = 0

    def _sweep(self, now: float) -> None:
        """Drop keys that have gone quiet for longer than the window.

        Args:
            now: the current monotonic timestamp.

        Called with the lock already held. Without it the table grows one
        entry per distinct client and never shrinks — a rate limiter that
        leaks memory is its own denial of service.
        """
        self._checks_since_sweep = 0
        cutoff = now - self._window_s
        stale = [key for key, hits in self._hits.items() if not hits or hits[-1] <= cutoff]
        for key in stale:
            del self._hits[key]


limiter = SlidingWindowLimiter(limit=RATE_LIMIT_PER_MINUTE)

# A separate, tighter allowance for /api/interpret. Deliberately its own number:
# /api/itinerary is limited to protect our CPU, while this one is limited
# because it spends someone else's quota — different reason, different budget.
INTERPRET_RATE_LIMIT_PER_MINUTE = int(os.environ.get("INTERPRET_RATE_LIMIT_PER_MINUTE", "5"))
interpret_limiter = SlidingWindowLimiter(limit=INTERPRET_RATE_LIMIT_PER_MINUTE)


def _enforce(limiter_: SlidingWindowLimiter, request: Request) -> None:
    """Refuse the caller with a 429 when they are over ``limiter_``'s allowance.

    Args:
        limiter_: the limiter holding this endpoint's allowance.
        request: the incoming request.

    Returns:
        None, when the request may proceed.

    Raises:
        HTTPException: 429, carrying ``Retry-After``, when over the limit.
    """
    retry_after = limiter_.check(client_ip(request))
    if retry_after is None:
        return
    raise HTTPException(
        status_code=429,
        detail="Too many requests — please wait a moment and try again.",
        # Whole seconds, rounded up, and never 0: a Retry-After of 0 invites
        # an immediate retry that would be refused again.
        headers={"Retry-After": str(max(1, math.ceil(retry_after)))},
    )


def enforce_rate_limit(request: Request) -> None:
    """FastAPI dependency guarding ``/api/itinerary``."""
    _enforce(limiter, request)


def enforce_interpret_rate_limit(request: Request) -> None:
    """FastAPI dependency guarding ``/api/interpret``."""
    _enforce(interpret_limiter, request)
