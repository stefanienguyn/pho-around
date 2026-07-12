"""End-to-end test of the public entry point on the real seed dataset."""

import time

from pho_engine import Start, load_seed_places, plan_itinerary

# A start point in the District 1 core (near Nhà Thờ Đức Bà).
DISTRICT_1 = Start(lat=10.7797, lng=106.6990, name="District 1")

TIME_BUDGET_MIN = 240  # a 4-hour outing
MONEY_BUDGET_VND = 400000


def test_realistic_query_respects_all_constraints() -> None:
    """Start D1, 4h, 400k → a sane, budget-respecting, non-repeating route."""
    places = load_seed_places()

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
    # ~30 places must solve fast enough to sit behind an API later.
    assert elapsed < 5.0, f"solve took {elapsed:.2f}s"
