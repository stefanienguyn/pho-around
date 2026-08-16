"""Travel-time layer for the itinerary engine.

For v1 we approximate travel time with straight-line (haversine) distance divided
by an assumed city speed — see ``wiki_storage/wiki/concepts/itinerary-optimization.md``
("Distances / travel time"). The solver depends only on ``travel_minutes``, so
swapping in real Google driving times in phase 3 is a one-function change.
"""

from __future__ import annotations

from math import asin, cos, radians, sin, sqrt
from typing import Protocol

# Mean Earth radius; standard value for haversine.
_EARTH_RADIUS_KM = 6371.0

# Measured average city speed (motorbike): median implied speed over the
# ≥2 km pairs of the real travel matrix (see data/travel_matrix.json _meta,
# fetched 2026-08-08, TWO_WHEELER). Used only as the fallback when the matrix
# or the live Routes call can't answer. Replaced the original 40 km/h guess,
# which measurement showed was ~3.7× optimistic.
CITY_SPEED_KMH = 12.6


class HasCoords(Protocol):
    """Anything with lat/lng — both ``Place`` and ``Start`` satisfy this."""

    lat: float
    lng: float


def haversine_km(a: HasCoords, b: HasCoords) -> float:
    """Great-circle distance in kilometres between two coordinates.

    Args:
        a, b: any objects exposing ``lat``/``lng`` in degrees.

    Returns:
        Distance in km (0.0 for identical coordinates). Symmetric in a, b.
    """
    lat1, lng1, lat2, lng2 = map(radians, (a.lat, a.lng, b.lat, b.lng))
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    # Haversine: h = sin²(Δlat/2) + cos(lat1)·cos(lat2)·sin²(Δlng/2)
    h = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlng / 2) ** 2
    return 2 * _EARTH_RADIUS_KM * asin(sqrt(h))


def travel_minutes(a: HasCoords, b: HasCoords, *, speed_kmh: float = CITY_SPEED_KMH) -> float:
    """Approximate travel time in minutes between two coordinates.

    Args:
        a, b: endpoints exposing ``lat``/``lng``.
        speed_kmh: assumed average speed; defaults to :data:`CITY_SPEED_KMH`.

    Returns:
        Minutes = haversine_km / speed_kmh · 60.
    """
    return haversine_km(a, b) / speed_kmh * 60.0
