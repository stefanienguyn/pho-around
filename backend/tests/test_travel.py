"""Tests for the travel-time lookup layer: matrix, fallbacks, and injection.

Everything here is offline — the matrix is a committed file, and the live
start legs are represented by plain dicts, exactly as the API layer passes
them in.
"""

import json

from pho_engine.distance import travel_minutes
from pho_engine.models import Place, Start
from pho_engine.seed import load_seed_places
from pho_engine.solver import plan_itinerary
from pho_engine.travel import _MATRIX_PATH, load_travel_matrix, make_travel_time_fn

START = Start(lat=10.7797, lng=106.6990)


def _tiny_place(id: str, *, lng: float) -> Place:
    """A minimal valid Place near the test start, for injection tests."""
    return Place(
        id=id,
        name=id,
        category="food",
        district="test",
        price_per_person_vnd=0,
        avg_minutes=10,
        score=4.0,
        lat=10.7797,
        lng=lng,
    )


def test_matrix_loads_and_matches_its_own_metadata() -> None:
    """Every pair in the committed file loads, and all times are plausible."""
    matrix = load_travel_matrix()
    meta = json.loads(_MATRIX_PATH.read_text(encoding="utf-8"))["_meta"]
    assert len(matrix) == meta["pairs"]
    assert all(0 < minutes <= 180 for minutes in matrix.values())


def test_lookup_prefers_the_matrix_over_the_formula() -> None:
    """A place→place question with a known cell answers from the matrix."""
    a, b = load_seed_places()[:2]
    matrix = load_travel_matrix()
    fn = make_travel_time_fn(matrix)
    assert fn(a, b) == matrix[(a.id, b.id)]
    assert fn(b, a) == matrix[(b.id, a.id)]  # ordered pairs: both directions exist


def test_missing_cell_falls_back_to_haversine() -> None:
    """An unknown pair degrades to the calibrated haversine estimate."""
    a, b = load_seed_places()[:2]
    fn = make_travel_time_fn({})  # empty matrix knows nothing
    assert fn(a, b) == travel_minutes(a, b)


def test_start_legs_answer_start_to_place() -> None:
    """The id-less start point uses the live legs when covered, formula when not."""
    covered, uncovered = load_seed_places()[:2]
    fn = make_travel_time_fn({}, start_legs={covered.id: 7.5})
    assert fn(START, covered) == 7.5
    assert fn(START, uncovered) == travel_minutes(START, uncovered)


def test_solver_consumes_injected_times() -> None:
    """plan_itinerary must route on injected answers, not its own formula.

    Two places sit meters from the start; the injected answerer claims "b" is
    999 minutes from everywhere. If the solver truly consumes the injection,
    "b" becomes unreachable despite its real proximity.
    """
    a = _tiny_place("a", lng=106.6991)
    b = _tiny_place("b", lng=106.6992)

    def poison(x: object, y: object) -> float:
        """Fake answerer: everything is 1 minute away, except reaching b."""
        return 999.0 if getattr(y, "id", None) == "b" else 1.0

    itin = plan_itinerary(
        [a, b], START, time_budget_min=60, money_budget_vnd=0, travel_time_fn=poison
    )
    assert itin.place_ids == ["a"]
