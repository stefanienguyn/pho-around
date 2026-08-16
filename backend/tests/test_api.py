"""HTTP tests for ``POST /api/itinerary`` (the phase-3 FastAPI layer).

These go through the full pipeline — routing, Pydantic validation, the
handler, the solver, JSON serialization — via FastAPI's ``TestClient``,
which calls the app in-process (no real network socket needed).
"""

import httpx2
import pytest
from fastapi.testclient import TestClient

import api
from api import app
from pho_engine import Start

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


# What a browser's CORS preflight sends alongside its Origin header.
PREFLIGHT_HEADERS = {
    "Access-Control-Request-Method": "POST",
    "Access-Control-Request-Headers": "Content-Type",
}


def test_cors_preflight_approves_the_vite_dev_origin() -> None:
    """The browser's OPTIONS scout from the Vite dev origin gets vouched for."""
    resp = client.options(
        "/api/itinerary",
        headers={"Origin": "http://localhost:5173", **PREFLIGHT_HEADERS},
    )
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_cors_preflight_rejects_an_unknown_origin() -> None:
    """A preflight from any other origin gets no approval header back."""
    resp = client.options(
        "/api/itinerary",
        headers={"Origin": "https://evil.example", **PREFLIGHT_HEADERS},
    )
    assert resp.status_code == 400
    assert "access-control-allow-origin" not in resp.headers


def test_tiny_budget_returns_empty_itinerary_not_an_error() -> None:
    """Nothing fits one minute → still 200, with empty stops and zero totals."""
    resp = client.post("/api/itinerary", json={**VALID_REQUEST, "time_budget_min": 1})

    assert resp.status_code == 200
    body = resp.json()
    assert body["stops"] == []
    assert body["total_score"] == 0.0
    assert body["total_cost_vnd"] == 0


def test_live_start_legs_flow_into_the_route(monkeypatch: pytest.MonkeyPatch) -> None:
    """When live legs exist, the first stop's travel time comes from them.

    Every place is claimed to be exactly 3 minutes from the start; whatever
    stop the solver picks first must therefore report 3.0 — proof the fetched
    legs reach the solver instead of being recomputed.
    """
    fake_legs = {place.id: 3.0 for place in api._PLACES}
    monkeypatch.setattr(api, "_fetch_start_legs", lambda start: fake_legs)
    resp = client.post("/api/itinerary", json=VALID_REQUEST)
    assert resp.status_code == 200
    assert resp.json()["stops"][0]["travel_minutes_from_prev"] == 3.0


def test_routes_outage_degrades_instead_of_failing(monkeypatch: pytest.MonkeyPatch) -> None:
    """A dead Routes API mid-request → still 200 with a full itinerary.

    The key is present (so a fetch is attempted) but the HTTP call raises;
    _fetch_start_legs must swallow it and the handler must fall back.
    """

    def boom(*args: object, **kwargs: object) -> object:
        raise httpx2.ConnectError("routes is down")

    monkeypatch.setattr(api, "_API_KEY", "fake-key-for-test")
    monkeypatch.setattr(api.httpx2, "post", boom)
    resp = client.post("/api/itinerary", json=VALID_REQUEST)
    assert resp.status_code == 200
    assert resp.json()["stops"], "degraded request must still produce a route"


def test_fetch_start_legs_parses_and_skips_bad_cells(monkeypatch: pytest.MonkeyPatch) -> None:
    """The Routes response parser keeps good cells and drops unroutable ones."""

    class FakeResponse:
        """Minimal stand-in for the httpx2 response the parser touches."""

        def raise_for_status(self) -> None:
            return None

        def json(self) -> list[dict]:
            return [
                {"destinationIndex": 0, "duration": "300s", "condition": "ROUTE_EXISTS"},
                {"destinationIndex": 1, "condition": "ROUTE_NOT_FOUND"},
            ]

    monkeypatch.setattr(api, "_API_KEY", "fake-key-for-test")
    monkeypatch.setattr(api.httpx2, "post", lambda *a, **k: FakeResponse())
    legs = api._fetch_start_legs(Start(lat=10.7797, lng=106.6990))
    assert legs == {api._PLACES[0].id: 5.0}
