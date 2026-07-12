"""HTTP tests for ``POST /api/itinerary`` (the phase-3 FastAPI layer).

These go through the full pipeline — routing, Pydantic validation, the
handler, the solver, JSON serialization — via FastAPI's ``TestClient``,
which calls the app in-process (no real network socket needed).
"""

from fastapi.testclient import TestClient

from api import app

client = TestClient(app)

# The same realistic query as tests/test_engine_e2e.py, on purpose: if that
# test passes and these fail, the bug is in the HTTP layer, not the engine.
VALID_REQUEST = {
    "start": {"lat": 10.7797, "lng": 106.6990},  # District 1 core
    "time_budget_min": 240,
    "money_budget_vnd": 400_000,
}


def test_happy_path_returns_budget_respecting_route() -> None:
    """A realistic query → 200 with an ordered, budget-honouring itinerary."""
    resp = client.post("/api/itinerary", json=VALID_REQUEST)

    assert resp.status_code == 200
    body = resp.json()
    assert body["stops"], "expected a non-empty itinerary for a generous budget"
    assert body["total_cost_vnd"] <= VALID_REQUEST["money_budget_vnd"]
    assert body["total_minutes"] <= VALID_REQUEST["time_budget_min"] + 1e-6
    # Stops are numbered 1..k in route order.
    assert [s["order"] for s in body["stops"]] == list(range(1, len(body["stops"]) + 1))
    # No place appears twice.
    ids = [s["place"]["id"] for s in body["stops"]]
    assert len(ids) == len(set(ids))


def test_missing_field_is_rejected() -> None:
    """Leaving out a required field → 422, before the handler ever runs."""
    incomplete = {"start": VALID_REQUEST["start"], "time_budget_min": 240}
    resp = client.post("/api/itinerary", json=incomplete)
    assert resp.status_code == 422


def test_negative_time_budget_is_rejected() -> None:
    """time_budget_min is declared gt=0; zero or negative → 422."""
    resp = client.post("/api/itinerary", json={**VALID_REQUEST, "time_budget_min": -30})
    assert resp.status_code == 422


def test_out_of_range_latitude_is_rejected() -> None:
    """lat is declared within [-90, 90]; 200 is not a latitude → 422."""
    bad = {**VALID_REQUEST, "start": {"lat": 200.0, "lng": 106.6990}}
    resp = client.post("/api/itinerary", json=bad)
    assert resp.status_code == 422


def test_tiny_budget_returns_empty_itinerary_not_an_error() -> None:
    """Nothing fits one minute → still 200, with empty stops and zero totals."""
    resp = client.post("/api/itinerary", json={**VALID_REQUEST, "time_budget_min": 1})

    assert resp.status_code == 200
    body = resp.json()
    assert body["stops"] == []
    assert body["total_score"] == 0.0
    assert body["total_cost_vnd"] == 0
