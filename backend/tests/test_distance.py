"""Tests for the haversine / travel-time layer."""

from pho_engine.distance import CITY_SPEED_KMH, haversine_km, travel_minutes
from pho_engine.models import Start


# Bến Thành Market and Nhà Thờ Đức Bà, ~0.85 km apart by hand calculation.
BEN_THANH = Start(lat=10.7721, lng=106.6980, name="Bến Thành")
NOTRE_DAME = Start(lat=10.7797, lng=106.6990, name="Notre-Dame")


def test_haversine_matches_hand_computed_distance() -> None:
    """Known Sài Gòn pair lands on its hand-computed ~0.852 km."""
    assert haversine_km(BEN_THANH, NOTRE_DAME) == round_close(0.852)


def test_haversine_is_symmetric_and_zero_on_identity() -> None:
    """d(a,b) == d(b,a) and d(a,a) == 0."""
    assert haversine_km(BEN_THANH, NOTRE_DAME) == haversine_km(NOTRE_DAME, BEN_THANH)
    assert haversine_km(BEN_THANH, BEN_THANH) == 0.0


def test_travel_minutes_uses_speed() -> None:
    """Minutes = km / speed · 60, using the default city speed."""
    km = haversine_km(BEN_THANH, NOTRE_DAME)
    assert travel_minutes(BEN_THANH, NOTRE_DAME) == km / CITY_SPEED_KMH * 60.0


def round_close(expected: float, *, tol: float = 0.02) -> object:
    """Helper: an object comparing equal to any float within ``tol``."""

    class _Close:
        def __eq__(self, other: object) -> bool:
            return isinstance(other, float) and abs(other - expected) < tol

        def __repr__(self) -> str:
            return f"~{expected}±{tol}"

    return _Close()
