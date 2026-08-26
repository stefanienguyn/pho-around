"""Tests for the model boundary — with the model itself replaced.

**No test here touches the network or spends a request of quota.** The model
call is monkeypatched everywhere; what these check is the machinery around it:
the schema we constrain the model to, the validation that decides what reaches
the solver, and every way the call can fail.

Measuring how well the model actually reads Vietnamese and English is a
different job with a different cost profile — that is the on-demand eval set,
deliberately not part of this gate.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import api
import interpret
import rate_limit
from api import app
from pho_engine.models import CATEGORIES

client = TestClient(app)

CATS = list(CATEGORIES)


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fresh rate-limit allowance, and no possible route to the network.

    Blanking the key matters more than it looks: a test that forgets to patch
    the model call would otherwise reach the real API and spend live quota.
    That happened once during development — with the key absent, the same
    mistake raises InterpretUnavailable instantly instead.
    """
    rate_limit.limiter.clear()
    rate_limit.interpret_limiter.clear()
    monkeypatch.setenv("GEMINI_API_KEY", "")


# --- The schema: what the model is physically able to emit -------------------


def test_schema_pins_every_open_value_to_a_closed_enum() -> None:
    """Categories and place ids can only be things that exist.

    This is the real defence. A plausible-looking id for a place we don't have
    is the likeliest failure of a language model here, and an enum makes it
    impossible to *generate* rather than something to catch afterwards.
    """
    ids = [p.id for p in api._PLACES]
    schema = interpret.response_schema(categories=CATS, place_ids=ids)
    props = schema["properties"]["constraints"]["items"]["properties"]

    assert props["type"]["enum"] == list(interpret.CONSTRAINT_TYPES)
    assert props["category"]["enum"] == CATS
    assert props["id"]["enum"] == ids
    assert "pho-that-isnt-real" not in props["id"]["enum"]


def test_schema_stays_small_enough_to_be_accepted() -> None:
    """Gemini rejects "very large or deeply nested" schemas.

    Kept flat rather than a seven-variant union of the real constraint types
    precisely to avoid that; this pins the decision so a later refactor to
    ``anyOf`` has to argue with a failing test.
    """
    import json

    ids = [p.id for p in api._PLACES]
    schema = interpret.response_schema(categories=CATS, place_ids=ids)
    assert len(json.dumps(schema)) < 20_000
    assert "anyOf" not in json.dumps(schema)


def test_prompt_names_every_real_place_and_leads_with_negation() -> None:
    """The catalogue lets require_place name real things; negation is rule one."""
    prompt = interpret.build_prompt(places=api._PLACES, categories=CATS)
    for place in api._PLACES:
        assert place.id in prompt
    assert "exclude_category, NOT min_category" in prompt


# --- Validation: what is allowed to reach the solver -------------------------


def test_valid_constraints_survive_and_unusable_ones_are_dropped() -> None:
    """One bad entry must not throw away the whole message.

    Enums make unknown values impossible, but a nonsense *combination* is still
    reachable — max_stops does not take a category, and no schema here says so.
    """
    valid, dropped = api.validate_constraints(
        [
            {"type": "exclude_category", "category": "shopping"},
            {"type": "max_stops", "count": 3},
            {"type": "max_stops", "category": "coffee"},  # count missing
            {"type": "require_place", "id": "pho-that-isnt-real"},  # not in the seed
        ]
    )
    assert [c.type for c in valid] == ["exclude_category", "max_stops"]
    assert dropped == 2


def test_validation_refuses_an_out_of_range_boost() -> None:
    """A boost is a nudge, not a veto — the clamp is enforced, not advisory."""
    _, dropped = api.validate_constraints(
        [{"type": "boost_category", "category": "coffee", "factor": 99}]
    )
    assert dropped == 1


# --- The endpoint ------------------------------------------------------------


def _fake_interpret(*constraints: dict, reply: str = "Got it."):
    """Build a stand-in for interpret.interpret returning fixed output."""

    def _call(message: str, **kwargs: object) -> tuple[list[dict], str]:
        return list(constraints), reply

    return _call


def test_happy_path_returns_validated_constraints(monkeypatch: pytest.MonkeyPatch) -> None:
    """A readable message becomes constraints the plan endpoint would accept."""
    monkeypatch.setattr(
        interpret,
        "interpret",
        _fake_interpret(
            {"type": "min_category", "category": "coffee", "count": 1},
            {"type": "exclude_category", "category": "shopping"},
            reply="Cà phê, không shopping.",
        ),
    )
    resp = client.post("/api/interpret", json={"message": "cà phê, không shopping"})

    assert resp.status_code == 200
    body = resp.json()
    assert [c["type"] for c in body["constraints"]] == ["min_category", "exclude_category"]
    assert body["reply"] == "Cà phê, không shopping."
    assert body["dropped"] == 0


def test_interpreted_constraints_are_accepted_by_the_plan_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The two endpoints actually compose — the real point of the contract.

    Whatever /api/interpret returns must be valid input to /api/itinerary, or
    the feature does not work end to end no matter how good the model is.
    """
    monkeypatch.setattr(
        interpret,
        "interpret",
        _fake_interpret({"type": "exclude_category", "category": "shopping"}),
    )
    interpreted = client.post("/api/interpret", json={"message": "no shopping"}).json()

    planned = client.post(
        "/api/itinerary",
        json={
            "start": {"lat": 10.7797, "lng": 106.6990},
            "time_budget_min": 240,
            "money_budget_vnd": 400_000,
            "constraints": interpreted["constraints"],
        },
    )
    assert planned.status_code == 200
    assert all(s["place"]["category"] != "shopping" for s in planned.json()["stops"])


def test_dropped_entries_are_reported_not_hidden(monkeypatch: pytest.MonkeyPatch) -> None:
    """A partly-understood request should say so rather than pretend."""
    monkeypatch.setattr(
        interpret,
        "interpret",
        _fake_interpret(
            {"type": "max_stops", "count": 3},
            {"type": "max_stops", "category": "coffee"},
        ),
    )
    body = client.post("/api/interpret", json={"message": "max 3 stops"}).json()
    assert len(body["constraints"]) == 1
    assert body["dropped"] == 1


def test_an_overlong_message_is_refused_before_the_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The length cap is enforced by the schema, so no quota is spent on it."""

    def must_not_be_called(*args: object, **kwargs: object) -> object:
        raise AssertionError("an over-long message must never reach the model")

    monkeypatch.setattr(interpret, "interpret", must_not_be_called)
    resp = client.post(
        "/api/interpret",
        json={"message": "x" * (interpret.MAX_MESSAGE_CHARS + 1)},
    )
    assert resp.status_code == 422


def test_no_key_is_a_503_not_a_crash(monkeypatch: pytest.MonkeyPatch) -> None:
    """A deployment without a key is missing a feature, not broken."""

    def unavailable(*args: object, **kwargs: object) -> object:
        raise interpret.InterpretUnavailable("GEMINI_API_KEY is not set")

    monkeypatch.setattr(interpret, "interpret", unavailable)
    resp = client.post("/api/interpret", json={"message": "coffee please"})
    assert resp.status_code == 503
    assert "sliders" in resp.json()["detail"]


def test_a_failed_model_call_degrades_to_502(monkeypatch: pytest.MonkeyPatch) -> None:
    """Gemini being down must not read as our bug, nor as a plan of no stops."""

    def failed(*args: object, **kwargs: object) -> object:
        raise interpret.InterpretFailed("connection reset")

    monkeypatch.setattr(interpret, "interpret", failed)
    resp = client.post("/api/interpret", json={"message": "coffee please"})
    assert resp.status_code == 502


def test_interpret_has_its_own_tighter_allowance(monkeypatch: pytest.MonkeyPatch) -> None:
    """Its limit is separate from the planner's: it spends someone else's quota."""
    assert rate_limit.INTERPRET_RATE_LIMIT_PER_MINUTE < rate_limit.RATE_LIMIT_PER_MINUTE
    monkeypatch.setattr(interpret, "interpret", _fake_interpret())

    hop = {"X-Forwarded-For": "203.0.113.90"}
    for _ in range(rate_limit.INTERPRET_RATE_LIMIT_PER_MINUTE):
        client.post("/api/interpret", json={"message": "coffee"}, headers=hop)

    resp = client.post("/api/interpret", json={"message": "coffee"}, headers=hop)
    assert resp.status_code == 429

    # The planner's allowance is untouched by the interpreter's traffic.
    plan = client.post(
        "/api/itinerary",
        json={
            "start": {"lat": 10.7797, "lng": 106.6990},
            "time_budget_min": 1,
            "money_budget_vnd": 50_000,
        },
        headers=hop,
    )
    assert plan.status_code == 200


def test_missing_key_is_detected_without_calling_anything(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """is_configured reads the environment; a blank key counts as missing."""
    monkeypatch.setenv("GEMINI_API_KEY", "   ")
    assert interpret.is_configured() is False
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-not-a-real-key")
    assert interpret.is_configured() is True


# --- Context: refining, without a server-side session ------------------------


def test_current_constraints_reach_the_prompt() -> None:
    """A follow-up can only edit what it is told is already set."""
    prompt = interpret.build_prompt(
        places=api._PLACES,
        categories=CATS,
        current=[{"type": "min_category", "category": "coffee", "count": 1}],
    )
    assert '"type": "min_category"' in prompt
    assert "ALREADY SET" in prompt
    assert "COMPLETE" in prompt, "the model must return the whole list, not a delta"


def test_no_context_is_a_clean_slate() -> None:
    """First message of a session: ALREADY SET is empty, not missing."""
    prompt = interpret.build_prompt(places=api._PLACES, categories=CATS)
    assert "ALREADY SET: []" in prompt


def test_the_endpoint_forwards_what_the_client_is_holding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The browser's constraint list is the memory, and it round-trips.

    Proves the wiring: what the client sends as context is what the model is
    shown. No session state exists on the server to get this wrong.
    """
    seen: dict[str, object] = {}

    def _capture(message: str, **kwargs: object) -> tuple[list[dict], str]:
        seen.update(kwargs)
        return [{"type": "min_category", "category": "coffee", "count": 2}], "Two coffees."

    monkeypatch.setattr(interpret, "interpret", _capture)
    resp = client.post(
        "/api/interpret",
        json={
            "message": "actually make it 2 coffees",
            "constraints": [{"type": "min_category", "category": "coffee", "count": 1}],
        },
    )

    assert resp.status_code == 200
    assert seen["current"] == [{"type": "min_category", "category": "coffee", "count": 1}]
    assert resp.json()["constraints"][0]["count"] == 2


def test_context_from_the_client_is_still_validated(monkeypatch: pytest.MonkeyPatch) -> None:
    """The browser is not trusted just because we were the ones who sent it.

    Anyone can POST anything; context arrives through the same closed
    vocabulary as every other input.
    """
    monkeypatch.setattr(interpret, "interpret", _fake_interpret())
    resp = client.post(
        "/api/interpret",
        json={
            "message": "more coffee",
            "constraints": [{"type": "require_place", "id": "pho-that-isnt-real"}],
        },
    )
    assert resp.status_code == 422
