"""One-time geocoder for the seed places (phase 3, chunk 2).

Looks up real coordinates for every place in ``pho_engine/data/seed_places.json``
via the Google Geocoding API and prints a before/after diff table. Writes
nothing unless ``--write`` is passed; rows with blocking flags (no match, or a
result outside the Sài Gòn sanity box) are never written. Never imported by
the API or the tests — run it by hand from ``app/backend/``:

    .venv/bin/python scripts/geocode_seed.py            # dry run: table only
    .venv/bin/python scripts/geocode_seed.py --write    # apply accepted rows
    .venv/bin/python scripts/geocode_seed.py --allow pho-le,oc-dao --write
                                    # also accept these human-reviewed big movers
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx2
from dotenv import load_dotenv

# Make pho_engine importable when run as a plain script from app/backend/.
_BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND_DIR))

from pho_engine.distance import haversine_km  # noqa: E402
from seed_io import write_seed  # noqa: E402

GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
PLACES_URL = "https://places.googleapis.com/v1/places:searchText"
# Bias circle for the Places fallback: "the branch I mean is within ~2 km of my old pin".
PLACES_BIAS_RADIUS_M = 2000.0
SEED_PATH = _BACKEND_DIR / "pho_engine" / "data" / "seed_places.json"
CITY_SUFFIX = "Hồ Chí Minh City, Vietnam"
# Sài Gòn sanity box — mirrors tests/test_seed.py; a hit outside it is a wrong match.
LAT_BOUNDS = (10.6, 11.0)
LNG_BOUNDS = (106.5, 106.8)
# Google's low-confidence location types: the point is inferred, not a found building.
LOW_CONFIDENCE_TYPES = {"APPROXIMATE", "RANGE_INTERPOLATED"}
BIG_MOVE_KM = 1.0
# Bias box half-width in degrees (~2 km): "prefer results near the old hand-placed pin".
# The hand-assigned coordinate encodes WHICH branch of a chain was meant.
BIAS_HALF_DEG = 0.02
NOTE_AFTER_GEOCODING = (
    "Machine-readable copy of wiki_storage/wiki/seed-places.md. lat/lng geocoded via the "
    "Google Geocoding API (phase 3, chunk 2); ids/names/prices/dwell/categories remain "
    "hand-curated. Keep the wiki table as the human-readable source of truth."
)


def geocode_place(
    client: httpx2.Client, *, name: str, district: str, near: SimpleNamespace, key: str
) -> dict | None:
    """Geocode one place by free-text address, biased toward its old pin.

    Args:
        client: shared HTTP client (connection reuse across the 30 calls).
        name: place name as curated in the seed data.
        district: seed district, used to disambiguate same-name branches.
        near: the old hand-assigned coordinate; a small ``bounds`` box around
            it tells Google "prefer results here" (bias, not a hard filter),
            which picks the intended branch of multi-branch chains.
        key: the backend API key (from the environment, never hardcoded).

    Returns:
        The first result dict from the Geocoding API, or None on ZERO_RESULTS
        (no guess is better than a wrong guess — the caller keeps the old
        coordinates).

    Raises:
        SystemExit: on any other non-OK status (denied key, quota, bad
        request) — a systemic refusal, not a per-place miss; retrying the
        remaining places would just burn 29 more calls.
    """
    address = f"{name}, {district}, {CITY_SUFFIX}"
    bounds = (
        f"{near.lat - BIAS_HALF_DEG},{near.lng - BIAS_HALF_DEG}|"
        f"{near.lat + BIAS_HALF_DEG},{near.lng + BIAS_HALF_DEG}"
    )
    response = client.get(GEOCODE_URL, params={"address": address, "bounds": bounds, "key": key})
    response.raise_for_status()
    payload = response.json()
    status = payload["status"]
    if status == "ZERO_RESULTS":
        return None
    if status != "OK":
        sys.exit(f"Geocoding API refused ({status}): {payload.get('error_message', 'no detail')}")
    return payload["results"][0]


def places_fallback(
    client: httpx2.Client, *, name: str, district: str, near: SimpleNamespace, key: str
) -> dict | None:
    """Look up a place via Places API (New) Text Search, biased near the old pin.

    The Geocoding API resolves *addresses* and shrugs at multi-branch business
    names; Text Search resolves *businesses* and honors a location bias — the
    right tool when geocoding's answer was blocked. Same API key (Places API
    (New) must be in its allowed list).

    Args:
        client: shared HTTP client.
        name: place name as curated in the seed data.
        district: seed district, included in the query text.
        near: the old hand-assigned coordinate, used as the bias circle center.
        key: the backend API key.

    Returns:
        A Geocoding-shaped result dict (so ``assess`` scores it identically),
        or None when the search returns no places.

    Raises:
        SystemExit: on a non-200 response — systemic refusal (API not
        enabled, key restriction, quota), not a per-place miss.
    """
    body = {
        "textQuery": f"{name}, {district}, {CITY_SUFFIX}",
        "locationBias": {
            "circle": {
                "center": {"latitude": near.lat, "longitude": near.lng},
                "radius": PLACES_BIAS_RADIUS_M,
            }
        },
        "pageSize": 1,
    }
    headers = {"X-Goog-Api-Key": key, "X-Goog-FieldMask": "places.location"}
    response = client.post(PLACES_URL, json=body, headers=headers)
    if response.status_code != 200:
        detail = response.json().get("error", {}).get("message", response.text[:200])
        sys.exit(f"Places API refused (HTTP {response.status_code}): {detail}")
    places = response.json().get("places", [])
    if not places:
        return None
    location = places[0]["location"]
    return {
        "geometry": {
            "location": {"lat": location["latitude"], "lng": location["longitude"]},
            # Not one of LOW_CONFIDENCE_TYPES: a Text Search hit is a found
            # business, not an inferred point.
            "location_type": "PLACES_TEXT_SEARCH",
        },
        "partial_match": False,
    }


def assess(place: dict[str, Any], result: dict | None, *, allowed: set[str]) -> dict[str, Any]:
    """Turn one place + its geocoding result into a diff row with flags.

    Args:
        place: the seed JSON row (old coordinates included).
        result: Google's top result for it, or None.
        allowed: place ids whose big moves a human has reviewed and approved
            (--allow); only the BIG MOVE block is waived — never the
            low-confidence/duplicate/out-of-bounds ones, which mark data that
            is objectively worse than the hand guess.

    Returns:
        A row dict: id, old/new coords, km moved, human-readable flags, and
        ``blocked`` (True → --write must keep the old coordinates).
    """
    old = SimpleNamespace(lat=place["lat"], lng=place["lng"])
    if result is None:
        return {
            "id": place["id"],
            "old": old,
            "new": None,
            "moved_km": 0.0,
            "flags": ["NO MATCH"],
            "blocked": True,
        }

    location = result["geometry"]["location"]
    new = SimpleNamespace(lat=location["lat"], lng=location["lng"])
    flags: list[str] = []
    blocked = False

    if not (LAT_BOUNDS[0] < new.lat < LAT_BOUNDS[1] and LNG_BOUNDS[0] < new.lng < LNG_BOUNDS[1]):
        flags.append("OUT OF BOUNDS")
        blocked = True
    if result.get("partial_match"):
        flags.append("PARTIAL")
    if result["geometry"]["location_type"] in LOW_CONFIDENCE_TYPES:
        # An inferred point (city/street-range centroid) is worse than our hand guess.
        flags.append("LOW CONFIDENCE")
        blocked = True

    moved_km = haversine_km(old, new)
    if moved_km > BIG_MOVE_KM:
        # A move this large is either a real correction or a wrong branch —
        # only a human can tell, so it blocks unless explicitly --allow'ed.
        if place["id"] in allowed:
            flags.append(f"BIG MOVE >{BIG_MOVE_KM:g} km (allowed)")
        else:
            flags.append(f"BIG MOVE >{BIG_MOVE_KM:g} km")
            blocked = True

    return {
        "id": place["id"],
        "old": old,
        "new": new,
        "moved_km": moved_km,
        "flags": flags,
        "blocked": blocked,
    }


def block_duplicate_points(rows: list[dict[str, Any]]) -> None:
    """Block every row whose new coordinate is shared with another row.

    Two different places resolving to the identical point is the fingerprint
    of Google falling back to a city/district centroid ("somewhere in Sài
    Gòn") — those answers are worse than the hand guesses they would replace.
    Mutates the rows in place.
    """
    by_point: dict[tuple[float, float], list[dict[str, Any]]] = {}
    for row in rows:
        if row["new"] is not None:
            point = (round(row["new"].lat, 5), round(row["new"].lng, 5))
            by_point.setdefault(point, []).append(row)
    for group in by_point.values():
        if len(group) > 1:
            for row in group:
                row["flags"].append("DUPLICATE POINT")
                row["blocked"] = True


def print_table(rows: list[dict[str, Any]]) -> None:
    """Print the before/after diff, one aligned line per place."""
    print(f"{'place':<24} {'old lat,lng':>18}  {'new lat,lng':>18} {'moved':>8}  flags")
    for row in rows:
        old = f"{row['old'].lat:.4f},{row['old'].lng:.4f}"
        if row["new"] is None:
            new, moved = "—", "—"
        else:
            new = f"{row['new'].lat:.4f},{row['new'].lng:.4f}"
            moved = f"{row['moved_km'] * 1000:.0f} m"
        print(f"{row['id']:<24} {old:>18}  {new:>18} {moved:>8}  {', '.join(row['flags'])}")


def main() -> None:
    """Geocode all seed places; print the diff; write back only with --write."""
    parser = argparse.ArgumentParser(description="Geocode the 30 seed places (dry-run default).")
    parser.add_argument(
        "--write", action="store_true", help="write accepted coordinates back into seed_places.json"
    )
    parser.add_argument(
        "--allow",
        default="",
        help="comma-separated place ids whose big moves were human-reviewed and approved",
    )
    args = parser.parse_args()
    allowed = {token.strip() for token in args.allow.split(",") if token.strip()}

    load_dotenv(_BACKEND_DIR / ".env")
    key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not key:
        sys.exit("GOOGLE_MAPS_API_KEY not set — create app/backend/.env (see .env.example).")

    seed = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    known_ids = {place["id"] for place in seed["places"]}
    unknown = allowed - known_ids
    if unknown:
        sys.exit(f"--allow names unknown place ids: {', '.join(sorted(unknown))}")

    rows: list[dict[str, Any]] = []
    with httpx2.Client(timeout=10.0) as client:
        for place in seed["places"]:
            near = SimpleNamespace(lat=place["lat"], lng=place["lng"])
            result = geocode_place(
                client, name=place["name"], district=place["district"], near=near, key=key
            )
            # The geocoding pass is always judged strictly (allowed=set()):
            # --allow blesses only the Places fallback's proposal — the value
            # the human actually reviewed in the diff. Waiving the geocoding
            # block directly would skip the fallback and write the unreviewed
            # geocoding answer instead.
            row = assess(place, result, allowed=set())
            if row["blocked"]:
                fallback = places_fallback(
                    client, name=place["name"], district=place["district"], near=near, key=key
                )
                if fallback is not None:
                    row = assess(place, fallback, allowed=allowed)
                    row["flags"].append("VIA PLACES")
            rows.append(row)

    block_duplicate_points(rows)
    print_table(rows)
    accepted = [row for row in rows if row["new"] is not None and not row["blocked"]]
    skipped = [row for row in rows if row not in accepted]
    print(f"\n{len(accepted)} accepted, {len(skipped)} kept unchanged (blocked/no match).")

    if not args.write:
        print("Dry run — nothing written. Re-run with --write to apply the accepted rows.")
        return

    new_by_id = {row["id"]: row["new"] for row in accepted}
    for place in seed["places"]:
        if place["id"] in new_by_id:
            place["lat"] = round(new_by_id[place["id"]].lat, 6)
            place["lng"] = round(new_by_id[place["id"]].lng, 6)
    seed["_note"] = NOTE_AFTER_GEOCODING
    # write_seed preserves the one-place-per-line layout (shared with the
    # discovery script via seed_io) so diffs show only real changes.
    write_seed(seed)
    print(f"Wrote {len(accepted)} updated coordinates to {SEED_PATH.name}.")


if __name__ == "__main__":
    main()
