"""End-to-end test of the public entry point on the real seed dataset."""

import time

from pho_engine import Start, load_seed_places, plan_itinerary
from pho_engine.candidates import K_BEST_FAR, K_NEAREST, select_candidates

# A start point in the District 1 core (near Nhà Thờ Đức Bà).
DISTRICT_1 = Start(lat=10.7797, lng=106.6990, name="District 1")

TIME_BUDGET_MIN = 240  # a 4-hour outing
MONEY_BUDGET_VND = 400000


def test_realistic_query_respects_all_constraints() -> None:
    """Start D1, 4h, 400k → a sane, budget-respecting, non-repeating route.

    Runs the same path the API does: pre-filter to ~40 candidates, then
    solve. The unfiltered 100-place seed blew the solver's 10 s cap — the
    filter IS the production architecture, so it's what this test times.
    """
    places = select_candidates(load_seed_places(), DISTRICT_1)
    assert len(places) == K_NEAREST + K_BEST_FAR

    started = time.perf_counter()
    itin = plan_itinerary(
        places,
        DISTRICT_1,
        time_budget_min=TIME_BUDGET_MIN,
        money_budget_vnd=MONEY_BUDGET_VND,
    )
    elapsed = time.perf_counter() - started

    assert itin.stops, "expected a non-empty itinerary for a generous budget"
    # No place appears twice.
    assert len(itin.place_ids) == len(set(itin.place_ids))
    # Both budgets are honoured (small float slack on time for travel rounding).
    assert itin.total_cost_vnd <= MONEY_BUDGET_VND
    assert itin.total_minutes <= TIME_BUDGET_MIN + 1e-6
    # The route is numbered from the depot outward.
    assert [s.order for s in itin.stops] == list(range(1, len(itin.stops) + 1))
    # The filtered instance must solve fast enough to sit behind the API —
    # this is the scale tripwire; if it fires, the candidate cap needs a look.
    assert elapsed < 5.0, f"solve took {elapsed:.2f}s"


def test_a_solver_timeout_still_returns_a_usable_plan() -> None:
    """A too-short time limit degrades to a good plan, never to an empty one.

    CBC reports "Not Solved" when the limit stops the search, but its incumbent
    is a feasible integer solution — the budget constraints held, only the
    optimality proof is missing. Discovered on Render's 0.1-CPU free tier, where
    the 4-hour query exceeds the cap and the API used to answer "nothing fits
    your budgets" while holding a route scoring 27.7.
    """
    places = select_candidates(load_seed_places(), DISTRICT_1)
    itin = plan_itinerary(
        places,
        DISTRICT_1,
        time_budget_min=TIME_BUDGET_MIN,
        money_budget_vnd=MONEY_BUDGET_VND,
        time_limit_s=1,
    )

    assert itin.stops, "a timed-out solve must still hand back its best route"
    # Feasibility is what branch and bound never gives up, so the budgets hold.
    assert itin.total_cost_vnd <= MONEY_BUDGET_VND
    assert itin.total_minutes <= TIME_BUDGET_MIN + 1e-6
    assert len(itin.place_ids) == len(set(itin.place_ids))
    assert [s.order for s in itin.stops] == list(range(1, len(itin.stops) + 1))
