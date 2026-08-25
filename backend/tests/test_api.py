"""HTTP tests for ``POST /api/itinerary`` (the phase-3 FastAPI layer).

These go through the full pipeline — routing, Pydantic validation, the
handler, the solver, JSON serialization — via FastAPI's ``TestClient``,
which calls the app in-process (no real network socket needed).
"""

import httpx2
import pytest
from fastapi.testclient import TestClient

import api
import rate_limit
from api import app
from pho_engine import Start
from pho_engine.candidates import select_candidates

client = TestClient(app)


@pytest.fixture(autouse=True)
def _fresh_rate_limit_allowance() -> None:
    """Give every test its own allowance.

    The limiter is process-global and every ``TestClient`` request presents
    the same identity, so without this the file's requests would accumulate
    into one bucket and later tests would start receiving 429s for calls made
    by earlier ones.
    """
    rate_limit.limiter.clear()


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
    monkeypatch.setattr(api, "_fetch_start_legs", lambda start, **kwargs: fake_legs)
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

    monkeypatch.setattr(api, "USE_LIVE_START_LEGS", True)
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

    monkeypatch.setattr(api, "USE_LIVE_START_LEGS", True)
    monkeypatch.setattr(api, "_API_KEY", "fake-key-for-test")
    monkeypatch.setattr(api.httpx2, "post", lambda *a, **k: FakeResponse())
    legs = api._fetch_start_legs(Start(lat=10.7797, lng=106.6990), places=api._PLACES)
    assert legs == {api._PLACES[0].id: 5.0}


# --- Constraints: the closed vocabulary at the HTTP boundary -----------------

GENEROUS = {**VALID_REQUEST, "time_budget_min": 300, "money_budget_vnd": 2_000_000}


def test_constraints_are_optional() -> None:
    """A request with no constraints field is still valid — clients keep working."""
    assert "constraints" not in VALID_REQUEST
    assert client.post("/api/itinerary", json=VALID_REQUEST).status_code == 200


def test_unknown_constraint_shapes_are_rejected() -> None:
    """Unknown type, category, place id, or out-of-range factor → 422.

    Nothing unvalidated may reach the model builder; this is the wall that
    makes it safe to put a language model behind the endpoint later.
    """
    bad_payloads = [
        {"type": "delete_everything"},
        {"type": "exclude_category", "category": "karaoke"},
        {"type": "require_place", "id": "not-a-real-place"},
        {"type": "boost_category", "category": "coffee", "factor": 99},
        {"type": "max_stops", "count": -1},
    ]
    for payload in bad_payloads:
        resp = client.post("/api/itinerary", json={**VALID_REQUEST, "constraints": [payload]})
        assert resp.status_code == 422, f"expected 422 for {payload}, got {resp.status_code}"


def test_excluded_category_never_appears_in_the_plan() -> None:
    """A hard filter removes the category before the model is even built."""
    resp = client.post(
        "/api/itinerary",
        json={**GENEROUS, "constraints": [{"type": "exclude_category", "category": "landmark"}]},
    )
    assert resp.status_code == 200
    categories = [stop["place"]["category"] for stop in resp.json()["stops"]]
    assert "landmark" not in categories


def test_required_place_survives_the_candidate_pre_filter() -> None:
    """A required place outside the default ~40 candidates still gets visited.

    Without must_include this is the designed-out bug: the place is filtered
    away, then pinned with visit[i]=1 while absent from the model — infeasible
    by construction, so the user's "we're definitely going here" would silently
    become an empty plan.
    """
    start = Start(lat=VALID_REQUEST["start"]["lat"], lng=VALID_REQUEST["start"]["lng"])
    default_ids = {place.id for place in select_candidates(api._PLACES, start)}
    outsider = next(place for place in api._PLACES if place.id not in default_ids)

    resp = client.post(
        "/api/itinerary",
        json={
            **GENEROUS,
            "constraints": [
                {"type": "require_place", "id": outsider.id},
                {"type": "max_stops", "count": 2},
            ],
        },
    )
    assert resp.status_code == 200
    assert outsider.id in [stop["place"]["id"] for stop in resp.json()["stops"]]


def test_impossible_constraints_return_an_empty_plan_not_an_error() -> None:
    """Constraints that fight each other → 200 with no stops, same as tight budgets."""
    resp = client.post(
        "/api/itinerary",
        json={
            **VALID_REQUEST,
            "time_budget_min": 45,
            "constraints": [{"type": "min_category", "category": "coffee", "count": 8}],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["stops"] == []


# --- Deployment configuration ------------------------------------------------


def test_allowlist_keeps_dev_origins_and_adds_configured_ones() -> None:
    """ALLOWED_ORIGINS is parsed leniently; dev origins always survive.

    The deployed frontend's origin differs per environment, so it arrives
    through configuration rather than being hardcoded. Blank values (the
    local case) must not produce an empty-string origin.
    """
    assert api.allowed_origins(None) == api.VITE_DEV_ORIGINS
    assert api.allowed_origins("") == api.VITE_DEV_ORIGINS
    assert api.allowed_origins("  ") == api.VITE_DEV_ORIGINS

    configured = api.allowed_origins(" https://pho.vercel.app , https://www.pho.app ")
    assert configured == [*api.VITE_DEV_ORIGINS, "https://pho.vercel.app", "https://www.pho.app"]


def test_live_start_legs_are_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """The default build spends nothing on Routes, even with a key present.

    The start legs are the only per-user-action Google cost (~25 Compute Route
    Matrix elements a click). They stay off unless USE_LIVE_START_LEGS is set,
    and the plan is built from the committed matrix + the calibrated haversine
    estimate instead.
    """

    def must_not_be_called(*args: object, **kwargs: object) -> object:
        raise AssertionError("the default build must not call the Routes API")

    monkeypatch.setattr(api, "_API_KEY", "fake-key-for-test")
    monkeypatch.setattr(api.httpx2, "post", must_not_be_called)

    assert api._fetch_start_legs(Start(lat=10.7797, lng=106.6990), places=api._PLACES) is None
    resp = client.post("/api/itinerary", json=VALID_REQUEST)
    assert resp.status_code == 200
    assert resp.json()["stops"], "a route must still be planned without live legs"


# These tests fire the whole allowance several times over, so they use a
# one-minute budget: nothing fits, the solve returns almost immediately, and
# the limiter — which runs in the dependency, before the handler — is exercised
# just as well. Planning real routes here would add ~30 s to the suite to test
# code that never runs.
CHEAP_REQUEST = {**VALID_REQUEST, "time_budget_min": 1}


def test_over_the_limit_gets_429_with_retry_after() -> None:
    """Past the allowance the API refuses, and says when to come back.

    The point is that the refusal happens in the dependency, so an abusive
    caller never reaches the solver — which is the expensive thing this
    protects.
    """
    hop = {"X-Forwarded-For": "203.0.113.50"}

    for _ in range(rate_limit.RATE_LIMIT_PER_MINUTE):
        assert client.post("/api/itinerary", json=CHEAP_REQUEST, headers=hop).status_code == 200

    resp = client.post("/api/itinerary", json=CHEAP_REQUEST, headers=hop)
    assert resp.status_code == 429
    assert int(resp.headers["Retry-After"]) >= 1


def test_two_clients_get_separate_allowances() -> None:
    """One noisy visitor must not lock everyone else out.

    Without proxy-aware identification this is exactly what would happen: all
    requests arrive from the host's proxy, so they would share one bucket.
    """
    noisy = {"X-Forwarded-For": "203.0.113.50"}
    quiet = {"X-Forwarded-For": "198.51.100.7"}

    for _ in range(rate_limit.RATE_LIMIT_PER_MINUTE + 1):
        client.post("/api/itinerary", json=CHEAP_REQUEST, headers=noisy)

    assert client.post("/api/itinerary", json=CHEAP_REQUEST, headers=noisy).status_code == 429
    assert client.post("/api/itinerary", json=CHEAP_REQUEST, headers=quiet).status_code == 200


def test_a_forged_forwarded_header_cannot_win_a_fresh_allowance() -> None:
    """Rotating the client-supplied hop must not reset the count.

    ``X-Forwarded-For`` is appended to, not replaced, so everything left of
    our proxy's entry is attacker-controlled. Keying on the leftmost value —
    the usual advice — would make the limiter trivially bypassable.
    """
    for i in range(rate_limit.RATE_LIMIT_PER_MINUTE):
        forged = {"X-Forwarded-For": f"10.0.0.{i}, 203.0.113.50"}
        assert client.post("/api/itinerary", json=CHEAP_REQUEST, headers=forged).status_code == 200

    another_forgery = {"X-Forwarded-For": "10.0.0.99, 203.0.113.50"}
    resp = client.post("/api/itinerary", json=CHEAP_REQUEST, headers=another_forgery)
    assert resp.status_code == 429, "the trusted rightmost hop is what counts"
