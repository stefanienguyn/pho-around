"""Unit tests for the rate limiter and its client-identification rule.

The HTTP-level behaviour (429s, ``Retry-After``, per-client buckets) is
covered in ``tests/test_api.py``; these exercise the mechanism directly, with
small limits and a fake clock so nothing has to sleep.
"""

from __future__ import annotations

import pytest

from rate_limit import SlidingWindowLimiter, client_ip


class FakeRequest:
    """The two attributes :func:`client_ip` reads, and nothing else."""

    def __init__(self, *, headers: dict[str, str] | None = None, host: str | None = None) -> None:
        self.headers = headers or {}
        self.client = None if host is None else type("Client", (), {"host": host})()


def test_allows_up_to_the_limit_then_refuses() -> None:
    """The nth request is fine; the (n+1)th is told how long to wait."""
    limiter = SlidingWindowLimiter(limit=3)

    assert [limiter.check("a") for _ in range(3)] == [None, None, None]

    retry_after = limiter.check("a")
    assert retry_after is not None
    assert 0 < retry_after <= 60


def test_keys_get_independent_buckets() -> None:
    """One client exhausting its allowance must not affect another."""
    limiter = SlidingWindowLimiter(limit=2)
    limiter.check("a")
    limiter.check("a")

    assert limiter.check("a") is not None, "the noisy client is limited"
    assert limiter.check("b") is None, "a different client is unaffected"


def test_the_window_slides(monkeypatch: pytest.MonkeyPatch) -> None:
    """Once the oldest hit ages out, the caller gets its allowance back."""
    clock = {"now": 1_000.0}
    monkeypatch.setattr("rate_limit.time.monotonic", lambda: clock["now"])

    limiter = SlidingWindowLimiter(limit=2, window_s=60.0)
    limiter.check("a")
    limiter.check("a")
    assert limiter.check("a") is not None

    clock["now"] += 61.0
    assert limiter.check("a") is None, "the window has rolled off"


def test_a_rejected_request_does_not_extend_the_lockout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Refusals aren't recorded, so hammering can't push the reset further out."""
    clock = {"now": 1_000.0}
    monkeypatch.setattr("rate_limit.time.monotonic", lambda: clock["now"])

    limiter = SlidingWindowLimiter(limit=1, window_s=60.0)
    limiter.check("a")

    # Keep knocking for most of the window.
    for _ in range(20):
        clock["now"] += 2.0
        assert limiter.check("a") is not None

    # The single recorded hit still expires 60 s after it happened.
    clock["now"] = 1_000.0 + 61.0
    assert limiter.check("a") is None


def test_quiet_keys_are_swept_so_the_table_cannot_grow_forever(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Buckets for clients that have gone silent are dropped, not kept."""
    clock = {"now": 1_000.0}
    monkeypatch.setattr("rate_limit.time.monotonic", lambda: clock["now"])
    monkeypatch.setattr("rate_limit._SWEEP_EVERY", 5)

    limiter = SlidingWindowLimiter(limit=10, window_s=60.0)
    for i in range(4):
        limiter.check(f"old-{i}")

    clock["now"] += 120.0
    # The 5th check triggers the sweep, which finds the four stale buckets.
    limiter.check("fresh")

    assert set(limiter._hits) == {"fresh"}


def test_client_ip_prefers_the_rightmost_forwarded_hop() -> None:
    """The proxy appends the true address; earlier hops are client-supplied."""
    request = FakeRequest(
        headers={"x-forwarded-for": "1.2.3.4, 203.0.113.9"},
        host="10.0.0.1",
    )
    assert client_ip(request) == "203.0.113.9"


def test_client_ip_ignores_a_forged_leading_hop() -> None:
    """Two callers forging different leading hops still share one bucket.

    This is the property that makes the limiter worth having: if the leftmost
    entry were trusted, anyone could invent a fresh address per request and
    never be limited at all.
    """
    a = FakeRequest(headers={"x-forwarded-for": "9.9.9.9, 203.0.113.9"})
    b = FakeRequest(headers={"x-forwarded-for": "8.8.8.8, 203.0.113.9"})
    assert client_ip(a) == client_ip(b) == "203.0.113.9"


def test_client_ip_falls_back_to_the_socket_then_to_unknown() -> None:
    """Without the header, use the peer address; without either, don't crash."""
    assert client_ip(FakeRequest(host="198.51.100.7")) == "198.51.100.7"
    assert client_ip(FakeRequest()) == "unknown"
