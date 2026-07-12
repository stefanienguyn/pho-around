"""Core data types for the itinerary engine.

These mirror the seed dataset schema documented in
``wiki_storage/wiki/seed-places.md`` and the model in
``wiki_storage/wiki/concepts/itinerary-optimization.md``. Everything the solver
reasons over is expressed with these plain, immutable records so the engine stays
a pure function that is easy to unit-test.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# The six categories the seed dataset (and the app) recognise. Kept here as the
# single source of truth so both the loader and any validation reuse it.
CATEGORIES: frozenset[str] = frozenset(
    {"food", "coffee", "dessert", "shopping", "photobooth", "landmark"}
)


@dataclass(frozen=True)
class Place:
    """One candidate place the engine may put on the itinerary.

    Fields match the seed schema. Money is whole VND, time is whole minutes,
    ``score`` is the 0–5 appeal used by the objective, and ``lat``/``lng`` are
    the (approximate, for v1) coordinates used to compute travel time.
    """

    id: str
    name: str
    category: str
    district: str
    price_per_person_vnd: int
    avg_minutes: int
    score: float
    lat: float
    lng: float
    tags: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Start:
    """The user's starting location — a depot node the route begins at.

    It is *not* one of the candidate places: it has no appeal, no dwell time and
    no cost. Only its coordinates matter (for the first leg's travel time).
    """

    lat: float
    lng: float
    name: str = "Start"


@dataclass(frozen=True)
class Stop:
    """One leg of a finished itinerary: a place plus how we got there.

    ``travel_minutes_from_prev`` is the travel time from the previous node
    (the depot for the first stop, otherwise the previous place).
    """

    order: int  # 1-based position in the route
    place: Place
    travel_minutes_from_prev: float


@dataclass(frozen=True)
class Itinerary:
    """The engine's output: an ordered, budget-respecting plan.

    Totals are precomputed so callers (and tests) never have to re-derive them.
    An empty ``stops`` list means nothing fit the budgets — a valid answer, not
    an error.
    """

    stops: tuple[Stop, ...]
    total_score: float
    total_minutes: float
    total_cost_vnd: int

    @property
    def place_ids(self) -> list[str]:
        """The visited place ids in route order (handy for assertions)."""
        return [stop.place.id for stop in self.stops]
