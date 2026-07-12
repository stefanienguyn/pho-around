"""Behavior tests for the MILP solver.

Each case is a tiny instance whose optimal answer is obvious by inspection, so a
wrong model fails loudly. Coordinates are chosen so haversine travel times are
easy to reason about (points spread along a line of latitude/longitude).
"""

from pho_engine.models import Place, Start
from pho_engine.solver import plan_itinerary

# A depot west of every test place, so the natural route runs west-to-east.
DEPOT = Start(lat=10.0, lng=106.0)


def make_place(
    id: str,
    *,
    score: float,
    price: int = 0,
    minutes: int = 10,
    lat: float = 10.0,
    lng: float = 106.0,
) -> Place:
    """Build a bare Place for tests, defaulting the fields a case doesn't care about."""
    return Place(
        id=id,
        name=id,
        category="food",
        district="test",
        price_per_person_vnd=price,
        avg_minutes=minutes,
        score=score,
        lat=lat,
        lng=lng,
    )


def test_single_place_within_budget_is_chosen() -> None:
    """Trivial: one affordable, reachable place → itinerary is just that place."""
    p = make_place("solo", score=4.0, price=50000, minutes=30, lng=106.005)
    itin = plan_itinerary([p], DEPOT, time_budget_min=120, money_budget_vnd=100000)
    assert itin.place_ids == ["solo"]
    assert itin.total_cost_vnd == 50000
    assert itin.total_score == 4.0


def test_money_budget_forces_the_higher_score_choice() -> None:
    """Two equally-priced places, budget affords one → the higher score wins."""
    a = make_place("rich", score=4.5, price=100000, lng=106.004)
    b = make_place("meh", score=4.0, price=100000, lng=106.006)
    itin = plan_itinerary([a, b], DEPOT, time_budget_min=120, money_budget_vnd=100000)
    assert itin.place_ids == ["rich"]
    assert itin.total_cost_vnd == 100000


def test_time_budget_excludes_the_far_place() -> None:
    """A far, higher-score place is unreachable in time → the near one is chosen.

    Proves the time constraint counts travel, not just dwell: 'far' scores more
    but sits ~55 km north, so its travel time blows the budget on its own.
    """
    near = make_place("near", score=3.0, minutes=20, lng=106.005)
    far = make_place("far", score=5.0, minutes=20, lat=10.5)  # ~55 km north
    itin = plan_itinerary([near, far], DEPOT, time_budget_min=30, money_budget_vnd=0)
    assert itin.place_ids == ["near"]


def test_route_is_ordered_to_minimize_travel() -> None:
    """Three collinear places with a tight time budget → the non-crossing order.

    Places sit on one line of latitude, 0.01° apart. Only the west-to-east
    ordering (a→b→c) keeps travel under budget; any crossing order costs more
    and would exceed it, so the solver is forced into the sensible route.
    """
    a = make_place("a", score=4.0, minutes=10, lng=106.01)
    b = make_place("b", score=4.0, minutes=10, lng=106.02)
    c = make_place("c", score=4.0, minutes=10, lng=106.03)
    # 30 min dwell + ~4.93 min minimal travel = ~34.9; the next-best order needs
    # ~36.6. A 35.5-min budget admits only the minimal (non-crossing) route.
    # stop_buffer_min=0 keeps this a pure routing-geometry test.
    itin = plan_itinerary(
        [a, b, c], DEPOT, time_budget_min=35.5, money_budget_vnd=0, stop_buffer_min=0
    )
    assert itin.place_ids == ["a", "b", "c"]


def test_loose_budget_still_picks_the_short_route() -> None:
    """The travel tiebreaker prevents zigzags when the time budget is generous.

    Regression: the objective only rewards score, so with a loose budget every
    ordering of the same three places scored identically and the solver returned
    a backtracking route (b->c->a, 8.2 min of travel instead of 4.9). The epsilon
    travel penalty breaks that tie toward the sensible west-to-east route.
    """
    a = make_place("a", score=4.0, minutes=10, lng=106.01)
    b = make_place("b", score=4.0, minutes=10, lng=106.02)
    c = make_place("c", score=4.0, minutes=10, lng=106.03)
    for budget in (60, 120, 600):  # all far looser than the ~35 min minimum
        itin = plan_itinerary(
            [a, b, c], DEPOT, time_budget_min=budget, money_budget_vnd=0, stop_buffer_min=0
        )
        assert itin.place_ids == ["a", "b", "c"], f"zigzag at budget {budget}"


def test_tiebreaker_never_drops_a_reachable_place() -> None:
    """Saving travel must never outweigh visiting a place.

    Guards the epsilon sizing: a far-but-affordable place is worth real score, so
    it must still be visited even though skipping it would save travel time.
    """
    near = make_place("near", score=4.0, minutes=10, lng=106.005)
    far = make_place("far", score=4.0, minutes=10, lng=106.30)  # ~33 km east
    itin = plan_itinerary([near, far], DEPOT, time_budget_min=120, money_budget_vnd=0)
    assert sorted(itin.place_ids) == ["far", "near"]


def test_tiebreaker_never_swaps_away_a_better_place() -> None:
    """Saving travel must never outweigh a *higher-scoring* place, only break ties.

    Regression: epsilon was first sized against the smallest score (4.2), leaving
    the maximum penalty (0.42) larger than the gap between two adjacent scores
    (4.3 vs 4.2 = 0.1) — so a far 4.3 lost to a near 4.2 and real score vanished.
    Epsilon is now bounded by the smallest score *gap*, which closes that.

    Both places fit the time budget on their own (dwell is only 10 min); the
    *money* budget forces exactly one. The better place is ~55 km away, so a
    tiebreaker that overreaches would wrongly prefer the nearer, worse one.
    """
    good = make_place("good", score=4.3, price=100000, minutes=10, lng=106.5)
    meh = make_place("meh", score=4.2, price=100000, minutes=10, lng=106.005)
    itin = plan_itinerary([good, meh], DEPOT, time_budget_min=120, money_budget_vnd=100000)
    assert itin.place_ids == ["good"]
    assert itin.total_score == 4.3


def test_stop_buffer_charges_real_world_friction_per_stop() -> None:
    """Each stop costs dwell + buffer, so the buffer scales with the stop count.

    Two 20-min places right next to the depot. With a 5-min buffer each, they cost
    ~50 min plus a little travel; a 48-min budget therefore fits only one of them,
    whereas with no buffer both would fit comfortably.
    """
    a = make_place("a", score=4.5, minutes=20, lng=106.001)
    b = make_place("b", score=4.0, minutes=20, lng=106.002)

    both = plan_itinerary(
        [a, b], DEPOT, time_budget_min=48, money_budget_vnd=0, stop_buffer_min=0
    )
    assert sorted(both.place_ids) == ["a", "b"], "without a buffer both stops fit"

    buffered = plan_itinerary(
        [a, b], DEPOT, time_budget_min=48, money_budget_vnd=0, stop_buffer_min=5
    )
    assert buffered.place_ids == ["a"], "the buffer must price out the second stop"
    # total_minutes must charge the buffer, or the plan under-reports its own cost.
    assert buffered.total_minutes >= 25.0


def test_zero_budgets_yield_an_empty_itinerary() -> None:
    """No time and no money → empty plan, not a crash."""
    p = make_place("nope", score=4.0, price=50000, minutes=30, lng=106.005)
    itin = plan_itinerary([p], DEPOT, time_budget_min=0, money_budget_vnd=0)
    assert itin.stops == ()
    assert itin.total_score == 0.0


def test_no_candidate_places_yields_an_empty_itinerary() -> None:
    """An empty candidate list is a valid (empty) answer."""
    itin = plan_itinerary([], DEPOT, time_budget_min=120, money_budget_vnd=100000)
    assert itin.stops == ()
