"""Real travel times for the engine: matrix lookup with haversine fallback.

The engine never fetches anything. This module reads the committed
``data/travel_matrix.json`` (built by ``scripts/build_travel_matrix.py``) and
builds the question-answering function that ``plan_itinerary`` accepts via its
``travel_time_fn`` parameter (dependency injection). The live per-request
start legs are fetched by the API layer, which passes them in as
``start_legs`` — no network code exists below this docstring.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from pho_engine.distance import HasCoords, travel_minutes

# Signature of the injected answerer: (from, to) -> minutes.
TravelTimeFn = Callable[[HasCoords, HasCoords], float]

_MATRIX_PATH = Path(__file__).parent / "data" / "travel_matrix.json"


def load_travel_matrix(*, path: Path | None = None) -> dict[tuple[str, str], float]:
    """Read the committed travel matrix into an ordered-pair lookup.

    Args:
        path: override the JSON location (used by tests). Defaults to the
            packaged ``data/travel_matrix.json``.

    Returns:
        Mapping of (origin_place_id, destination_place_id) → travel minutes.
        Ordered pairs: (a, b) and (b, a) are distinct entries (one-way streets).
    """
    raw = json.loads((path or _MATRIX_PATH).read_text(encoding="utf-8"))
    minutes: dict[tuple[str, str], float] = {}
    for pair, mins in raw["minutes"].items():
        origin_id, dest_id = pair.split("|")
        minutes[(origin_id, dest_id)] = float(mins)
    return minutes


def make_travel_time_fn(
    matrix: dict[tuple[str, str], float], *, start_legs: dict[str, float] | None = None
) -> TravelTimeFn:
    """Build the travel-time answerer the solver gets injected with.

    Answer priority for a→b:
      1. the real matrix, when both endpoints are places it knows;
      2. ``start_legs``, when a is the (id-less) start point and b is covered;
      3. the haversine estimate at the calibrated city speed — the graceful-
         degradation floor, which also covers the few cells flagged away at
         matrix-build time.

    Args:
        matrix: ordered-pair travel times from :func:`load_travel_matrix`.
        start_legs: optional map of place id → minutes from the request's
            start point (fetched live by the API layer; absent in tests and
            whenever the live call failed).

    Returns:
        A ``TravelTimeFn`` for ``plan_itinerary(travel_time_fn=...)``.
    """
    legs = start_legs or {}

    def travel_time(a: HasCoords, b: HasCoords) -> float:
        """Answer 'minutes from a to b' from the best available source."""
        a_id = getattr(a, "id", None)
        b_id = getattr(b, "id", None)
        if a_id is not None and b_id is not None:
            real = matrix.get((a_id, b_id))
            if real is not None:
                return real
        elif a_id is None and b_id is not None and b_id in legs:
            return legs[b_id]
        return travel_minutes(a, b)

    return travel_time
