"""HTTP API for Phở around (phase 3, step 1).

One endpoint — ``POST /api/itinerary`` — wraps the phase-2 engine's
:func:`pho_engine.plan_itinerary` behind an HTTP contract. The Pydantic models
below *are* that contract: request models declare what clients must send (and
FastAPI rejects anything else with a 422 before the handler runs); response
models declare what we promise back. They deliberately mirror — but stay
separate from — the engine's internal dataclasses, so the engine can be
refactored without breaking clients.

The endpoint is stateless: nothing is persisted, per the v1 roadmap
(``wiki_storage/wiki/concepts/v1-scope-and-roadmap.md``).

Run locally (from ``app/backend/``)::

    .venv/bin/uvicorn api:app --reload

then try it interactively at http://127.0.0.1:8000/docs
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import httpx2
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from pho_engine import Itinerary, Start, load_seed_places, plan_itinerary
from pho_engine.travel import load_travel_matrix, make_travel_time_fn

logger = logging.getLogger(__name__)

# --- Request schemas: what clients send ----------------------------------


class StartIn(BaseModel):
    """The user's starting location (the route's depot)."""

    lat: float = Field(ge=-90, le=90, description="Latitude, decimal degrees")
    lng: float = Field(ge=-180, le=180, description="Longitude, decimal degrees")


class ItineraryRequest(BaseModel):
    """A plan request: where you are, how long you have, what you can spend."""

    start: StartIn
    time_budget_min: float = Field(gt=0, description="Total minutes available")
    money_budget_vnd: int = Field(ge=0, description="Total spend allowed, in VND")


# --- Response schemas: what we promise back -------------------------------


class PlaceOut(BaseModel):
    """One recommended place, as exposed to clients (all fields are public)."""

    id: str
    name: str
    category: str
    district: str
    price_per_person_vnd: int
    avg_minutes: int
    score: float
    lat: float
    lng: float
    tags: list[str]


class StopOut(BaseModel):
    """One leg of the returned route: a place plus the travel to reach it."""

    order: int
    place: PlaceOut
    travel_minutes_from_prev: float


class ItineraryResponse(BaseModel):
    """The optimized plan. Empty ``stops`` means nothing fit the budgets —
    a valid answer (still HTTP 200), not an error."""

    stops: list[StopOut]
    total_score: float
    total_minutes: float
    total_cost_vnd: int


# The 30 seed places, loaded once at startup. They are immutable, so there is
# no reason to re-read the JSON file per request.
_PLACES = load_seed_places()

# The committed place-to-place travel matrix (real motorbike minutes), loaded
# once — like the seed, it only changes when the data files change.
_MATRIX = load_travel_matrix()

# Backend key for the per-request start legs. Optional on purpose: with no key
# (tests, offline dev) the API still works — travel falls back to matrix +
# haversine, per the graceful-degradation design.
load_dotenv(Path(__file__).parent / ".env")
_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY")
if not _API_KEY:
    logger.warning("GOOGLE_MAPS_API_KEY not set — start legs will use the haversine fallback")

ROUTES_MATRIX_URL = "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix"
# Must match the mode the committed matrix was built with (_meta in the JSON).
TRAVEL_MODE = "TWO_WHEELER"
# Cap on how long the live call may hold up a response; past this we fall back.
LIVE_LEGS_TIMEOUT_S = 1.5


def _waypoint(point: Start) -> dict:
    """Shape one lat/lng into the Routes API's waypoint structure."""
    return {"waypoint": {"location": {"latLng": {"latitude": point.lat, "longitude": point.lng}}}}


def _fetch_start_legs(start: Start) -> dict[str, float] | None:
    """Fetch live, traffic-aware start→place minutes for every seed place.

    Args:
        start: the request's starting point.

    Returns:
        Map of place id → minutes, or None when the legs are unavailable (no
        key, timeout, HTTP error, malformed response) — the caller then relies
        on the haversine fallback. Failures are logged, never raised: a route
        with estimated start legs beats no route (graceful degradation).
    """
    if not _API_KEY:
        return None
    body = {
        "origins": [_waypoint(start)],
        "destinations": [_waypoint(place) for place in _PLACES],
        "travelMode": TRAVEL_MODE,
        # Unlike the committed matrix, these 30 cells are cheap per-request —
        # so they get live traffic, the one place we can afford it.
        "routingPreference": "TRAFFIC_AWARE",
    }
    headers = {
        "X-Goog-Api-Key": _API_KEY,
        "X-Goog-FieldMask": "destinationIndex,duration,condition",
    }
    try:
        response = httpx2.post(
            ROUTES_MATRIX_URL, json=body, headers=headers, timeout=LIVE_LEGS_TIMEOUT_S
        )
        response.raise_for_status()
        legs: dict[str, float] = {}
        for cell in response.json():
            if cell.get("condition") != "ROUTE_EXISTS" or "duration" not in cell:
                continue
            place_id = _PLACES[cell.get("destinationIndex", 0)].id
            legs[place_id] = int(cell["duration"].rstrip("s")) / 60.0
        return legs or None
    except (httpx2.HTTPError, ValueError, KeyError, IndexError) as exc:
        logger.warning("live start legs unavailable, falling back to haversine: %s", exc)
        return None


app = FastAPI(
    title="Phở around API",
    description="Optimized Sài Gòn itineraries from a start point, a time "
    "budget and a money budget (orienteering MILP under the hood).",
    version="0.1.0",
)

# The only browser origins allowed to call this API cross-origin: the Vite
# dev server. CORS controls which *pages* a browser lets read our responses;
# it is not authentication (curl and scripts are unaffected by it).
VITE_DEV_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=VITE_DEV_ORIGINS,
    allow_methods=["POST"],
    allow_headers=["Content-Type"],
)


def _to_response(itinerary: Itinerary) -> ItineraryResponse:
    """Translate the engine's internal ``Itinerary`` into the API response.

    This explicit field-by-field mapping is the boundary between the engine's
    types and the public contract — the one place to reconcile them if either
    side changes shape.
    """
    return ItineraryResponse(
        stops=[
            StopOut(
                order=stop.order,
                place=PlaceOut(
                    id=stop.place.id,
                    name=stop.place.name,
                    category=stop.place.category,
                    district=stop.place.district,
                    price_per_person_vnd=stop.place.price_per_person_vnd,
                    avg_minutes=stop.place.avg_minutes,
                    score=stop.place.score,
                    lat=stop.place.lat,
                    lng=stop.place.lng,
                    tags=list(stop.place.tags),
                ),
                travel_minutes_from_prev=stop.travel_minutes_from_prev,
            )
            for stop in itinerary.stops
        ],
        total_score=itinerary.total_score,
        total_minutes=itinerary.total_minutes,
        total_cost_vnd=itinerary.total_cost_vnd,
    )


@app.post("/api/itinerary", response_model=ItineraryResponse)
def create_itinerary(request: ItineraryRequest) -> ItineraryResponse:
    """Compute the best itinerary for the given start point and budgets.

    Declared as a plain ``def`` (not ``async def``) on purpose: the CBC solve
    is ~2.5 s of pure CPU, so FastAPI must run it in its worker threadpool —
    an ``async def`` handler would block the event loop for every concurrent
    request until the solver finished.
    """
    start = Start(lat=request.start.lat, lng=request.start.lng)
    itinerary = plan_itinerary(
        _PLACES,
        start,
        time_budget_min=request.time_budget_min,
        money_budget_vnd=request.money_budget_vnd,
        # Real travel times: committed matrix for place→place, live legs for
        # start→place, haversine as the floor (see pho_engine/travel.py).
        travel_time_fn=make_travel_time_fn(_MATRIX, start_legs=_fetch_start_legs(start)),
    )
    return _to_response(itinerary)
