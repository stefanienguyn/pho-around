"""Behavior tests for the MILP solver.

Each case is a tiny instance whose optimal answer is obvious by inspection, so a
wrong model fails loudly. Coordinates are chosen so haversine travel times are
easy to reason about (points spread along a line of latitude/longitude).
"""

import pytest

from pho_engine.constraints import (
    FirstCategory,
    FirstPlace,
    BoostCategory,
    ExcludeCategory,
    MaxCategory,
    MaxStops,
    MinCategory,
    RequirePlace,
)
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
    # speed pinned at 40: the minute math above was derived at that speed, and
    # this test targets routing geometry, not the calibrated city constant.
    itin = plan_itinerary(
        [a, b, c], DEPOT, time_budget_min=35.5, money_budget_vnd=0, stop_buffer_min=0, speed_kmh=40
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
    # speed pinned at 40 so "far" stays reachable within the budget — the test
    # targets epsilon sizing, and its premise (feasibility) must not drift with
    # the calibrated constant.
    itin = plan_itinerary([near, far], DEPOT, time_budget_min=120, money_budget_vnd=0, speed_kmh=40)
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
    # speed pinned at 40: keeps "good" reachable, so the money budget (not
    # travel feasibility) stays the thing forcing the choice.
    itin = plan_itinerary(
        [good, meh], DEPOT, time_budget_min=120, money_budget_vnd=100000, speed_kmh=40
    )
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

    both = plan_itinerary([a, b], DEPOT, time_budget_min=48, money_budget_vnd=0, stop_buffer_min=0)
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


# --- Constraints & variety (the LLM layer's deterministic half) --------------


def make_categorised(id: str, *, category: str, score: float, lng: float) -> Place:
    """A place whose category matters; near the depot so travel never binds."""
    return Place(
        id=id,
        name=id,
        category=category,
        district="test",
        price_per_person_vnd=0,
        avg_minutes=10,
        score=score,
        lat=10.0,
        lng=lng,
    )


# Two categories, interleaved, all reachable: coffee scores slightly higher, so
# an unconstrained plan takes coffee first and variety is the only thing that
# can pull a food place in.
VARIETY_CASE = [
    make_categorised("coffee-a", category="coffee", score=4.6, lng=106.001),
    make_categorised("coffee-b", category="coffee", score=4.5, lng=106.002),
    make_categorised("coffee-c", category="coffee", score=4.4, lng=106.003),
    make_categorised("food-a", category="food", score=4.3, lng=106.004),
]


def test_variety_penalty_breaks_up_a_single_category_run() -> None:
    """Three near-identical cafés → the default objective reaches for the food.

    Without the penalty the top three scores are all coffee. Charging 0.3 for
    each repeat makes the third coffee (4.4 - 0.3 - 0.3) worth less than the
    food place (4.3), so a sane afternoon appears on its own.
    """
    itin = plan_itinerary(
        VARIETY_CASE, DEPOT, time_budget_min=90, money_budget_vnd=0, stop_buffer_min=0
    )
    categories = [s.place.category for s in itin.stops]
    assert "food" in categories, f"expected variety, got {categories}"


def test_variety_is_soft_not_a_cap() -> None:
    """With the penalty off, the same instance happily stacks one category.

    Proves the penalty is what changed the plan (not the budgets), and that
    repeats remain *possible* — taste is soft.
    """
    itin = plan_itinerary(
        VARIETY_CASE,
        DEPOT,
        time_budget_min=90,
        money_budget_vnd=0,
        stop_buffer_min=0,
        variety_penalties={},
    )
    assert [s.place.category for s in itin.stops].count("coffee") == 3


def test_boost_shifts_the_choice_without_forcing_it() -> None:
    """A category boost lifts effective appeal enough to win a money-forced pick."""
    coffee = make_categorised("coffee", category="coffee", score=4.0, lng=106.001)
    food = make_categorised("food", category="food", score=4.4, lng=106.002)
    both = [coffee, food]
    priced = [Place(**{**vars(p), "price_per_person_vnd": 100000, "tags": p.tags}) for p in both]
    plain = plan_itinerary(priced, DEPOT, time_budget_min=120, money_budget_vnd=100000)
    assert plain.place_ids == ["food"], "unboosted, the higher raw score wins"

    boosted = plan_itinerary(
        priced,
        DEPOT,
        time_budget_min=120,
        money_budget_vnd=100000,
        constraints=[BoostCategory(category="coffee", factor=1.25)],
    )
    assert boosted.place_ids == ["coffee"], "4.0 * 1.25 = 5.0 should now outrank 4.4"
    # Raw appeal is reported, never the weighted number the objective traded in.
    assert boosted.total_score == 4.0


def test_epsilon_still_protects_a_better_place_when_scores_are_weighted() -> None:
    """The July swap bug, re-armed by category boosts (the epsilon trap).

    Boosting the near place's category narrows the effective gap to 0.025
    (4.4 vs 3.5 * 1.25 = 4.375). An epsilon sized from *raw* scores would be
    large enough to prefer the near, worse place; sized from effective scores
    it cannot. Money forces exactly one pick, as in the original regression.
    """
    good = make_place("good", score=4.4, price=100000, minutes=10, lng=106.5)
    meh = make_categorised("meh", category="coffee", score=3.5, lng=106.005)
    meh = Place(**{**vars(meh), "price_per_person_vnd": 100000})
    itin = plan_itinerary(
        [good, meh],
        DEPOT,
        time_budget_min=120,
        money_budget_vnd=100000,
        speed_kmh=40,
        constraints=[BoostCategory(category="coffee", factor=1.25)],
    )
    assert itin.place_ids == ["good"], "epsilon must not swap away the better place"


def test_exclusions_and_requirements_are_honoured() -> None:
    """exclude_category removes a whole category; require_place pins one in."""
    excluded = plan_itinerary(
        VARIETY_CASE,
        DEPOT,
        time_budget_min=90,
        money_budget_vnd=0,
        stop_buffer_min=0,
        constraints=[ExcludeCategory(category="coffee")],
    )
    assert excluded.place_ids == ["food-a"]

    required = plan_itinerary(
        VARIETY_CASE,
        DEPOT,
        time_budget_min=25,  # only room for one stop
        money_budget_vnd=0,
        stop_buffer_min=0,
        constraints=[RequirePlace(id="coffee-c")],
    )
    assert "coffee-c" in required.place_ids, "a required place must appear"


def test_category_bounds_and_max_stops_are_honoured() -> None:
    """min/max per category and the overall stop ceiling each bind."""
    capped = plan_itinerary(
        VARIETY_CASE,
        DEPOT,
        time_budget_min=90,
        money_budget_vnd=0,
        stop_buffer_min=0,
        constraints=[MaxCategory(category="coffee", count=1)],
    )
    assert [s.place.category for s in capped.stops].count("coffee") == 1

    two_stops = plan_itinerary(
        VARIETY_CASE,
        DEPOT,
        time_budget_min=90,
        money_budget_vnd=0,
        stop_buffer_min=0,
        constraints=[MaxStops(count=2)],
    )
    assert len(two_stops.stops) == 2

    with_food = plan_itinerary(
        VARIETY_CASE,
        DEPOT,
        time_budget_min=40,
        money_budget_vnd=0,
        stop_buffer_min=0,
        constraints=[MinCategory(category="food", count=1)],
    )
    assert "food-a" in with_food.place_ids


def test_requiring_a_place_outside_the_candidate_set_fails_loudly() -> None:
    """Pinning a place that never became a variable is a caller bug, not a plan.

    The API layer force-includes required ids in the candidate set; if that
    ever regresses we want a loud error, not a silently dropped requirement.
    """
    with pytest.raises(ValueError, match="required places absent"):
        plan_itinerary(
            VARIETY_CASE,
            DEPOT,
            time_budget_min=90,
            money_budget_vnd=0,
            constraints=[RequirePlace(id="not-in-this-list")],
        )


def test_satiation_rate_differs_by_category() -> None:
    """Landmarks may repeat cheaply; coffee may not — the per-category rate.

    Four places, money forces exactly three. Repeating landmarks costs 0.2 and
    repeating coffee costs 1.0, so the best three are both landmarks plus the
    better coffee — never two coffees. A single global penalty could not
    express this: it would either wave both repeats through or block both.
    """
    priced = [
        Place(**{**vars(p), "price_per_person_vnd": 100000})
        for p in (
            make_categorised("landmark-a", category="landmark", score=4.5, lng=106.001),
            make_categorised("landmark-b", category="landmark", score=4.4, lng=106.002),
            make_categorised("coffee-a", category="coffee", score=4.5, lng=106.003),
            make_categorised("coffee-b", category="coffee", score=4.4, lng=106.004),
        )
    ]
    itin = plan_itinerary(
        priced, DEPOT, time_budget_min=120, money_budget_vnd=300000, stop_buffer_min=0
    )
    categories = [s.place.category for s in itin.stops]
    assert len(itin.stops) == 3
    assert categories.count("landmark") == 2, f"landmarks repeat cheaply, got {categories}"
    assert categories.count("coffee") == 1, f"coffee should not repeat, got {categories}"


def test_first_place_overrides_the_travel_order() -> None:
    """The shortest loop is a→b→c; anchoring c first flips the sequence.

    Same collinear layout as the ordering test, but with a loose budget so
    every order is feasible — the anchor, not the budget, decides. Without
    the anchor the tiebreaker still yields a→b→c (guarded below), so the
    test cannot pass by accident.
    """
    a = make_place("a", score=4.0, minutes=10, lng=106.01)
    b = make_place("b", score=4.0, minutes=10, lng=106.02)
    c = make_place("c", score=4.0, minutes=10, lng=106.03)
    common = dict(time_budget_min=120, money_budget_vnd=0, stop_buffer_min=0, speed_kmh=40)

    assert plan_itinerary([a, b, c], DEPOT, **common).place_ids == ["a", "b", "c"]
    anchored = plan_itinerary([a, b, c], DEPOT, constraints=[FirstPlace(id="c")], **common)
    assert anchored.place_ids[0] == "c"
    assert set(anchored.place_ids) == {"a", "b", "c"}


def test_first_category_picks_some_member_of_that_category_first() -> None:
    """Anchor by category: the first stop is coffee, the solver chooses which."""
    food = make_place("food", score=4.0, minutes=10, lng=106.01)
    cafe = make_categorised("cafe", category="coffee", score=4.0, lng=106.03)
    itin = plan_itinerary(
        [food, cafe],
        DEPOT,
        time_budget_min=120,
        money_budget_vnd=0,
        stop_buffer_min=0,
        speed_kmh=40,
        constraints=[FirstCategory(category="coffee")],
    )
    assert itin.place_ids[0] == "cafe"


def test_first_category_with_no_member_yields_an_empty_plan() -> None:
    """An impossible anchor is an empty plan, never a crash."""
    food = make_place("food", score=4.0, minutes=10, lng=106.01)
    itin = plan_itinerary(
        [food],
        DEPOT,
        time_budget_min=120,
        money_budget_vnd=0,
        constraints=[FirstCategory(category="coffee")],
    )
    assert itin.stops == ()
