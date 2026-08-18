"""One-time builder for the place-to-place travel-time matrix (phase 3, chunk 3).

Fetches real travel times for every ordered pair of seed places from the Routes
API ``computeRouteMatrix`` endpoint and compares them against the haversine
÷ CITY_SPEED_KMH estimate the engine has used since phase 2. Writes nothing
unless ``--write`` is passed; implausible or missing cells are flagged and left
out of the matrix (the runtime lookup falls back to haversine per-cell). Never
imported by the API or tests — run by hand from ``app/backend/``:

    .venv/bin/python scripts/build_travel_matrix.py             # dry run: report only
    .venv/bin/python scripts/build_travel_matrix.py --write     # also write the JSON
    .venv/bin/python scripts/build_travel_matrix.py --mode DRIVE --write
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path
from statistics import mean, median
from types import SimpleNamespace
from typing import Any

import httpx2
from dotenv import load_dotenv

# Make pho_engine importable when run as a plain script from app/backend/.
_BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND_DIR))

from pho_engine.distance import CITY_SPEED_KMH, haversine_km, travel_minutes  # noqa: E402

MATRIX_URL = "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix"
SEED_PATH = _BACKEND_DIR / "pho_engine" / "data" / "seed_places.json"
MATRIX_PATH = _BACKEND_DIR / "pho_engine" / "data" / "travel_matrix.json"
DEFAULT_MODE = "TWO_WHEELER"
# The API caps elements (origins × destinations) per request; origins are
# sliced so each request stays under the cap. Same total cost either way.
MAX_ELEMENTS_PER_REQUEST = 625
# Plausibility bounds for one leg within the city; cells outside are flagged
# and omitted (the runtime lookup falls back to haversine for missing cells).
MIN_PLAUSIBLE_MIN = 0.5
MAX_PLAUSIBLE_MIN = 180.0
TOP_N = 5
# Calibrate the fallback speed only on pairs long enough that riding dominates
# the parking/maneuvering overhead which makes short-hop "speeds" meaningless.
CALIBRATION_MIN_KM = 2.0


def _waypoint(place: dict[str, Any]) -> dict:
    """Shape one seed row into the Routes API's waypoint structure."""
    return {
        "waypoint": {"location": {"latLng": {"latitude": place["lat"], "longitude": place["lng"]}}}
    }


def fetch_matrix(
    client: httpx2.Client,
    *,
    places: list[dict[str, Any]],
    mode: str,
    key: str,
    nearest: int | None = None,
) -> tuple[dict[tuple[str, str], float], list[str]]:
    """Fetch real travel minutes between places — full grid or k-nearest.

    Args:
        client: shared HTTP client.
        places: seed rows (id/lat/lng used).
        mode: Routes API travel mode (e.g. TWO_WHEELER, DRIVE).
        key: the backend API key.
        nearest: None = every ordered pair (n·(n−1) elements — fine at ~30
            places, wasteful at 100 where distant pairs are never ridden);
            k = each place → only its k nearest neighbours (n·k elements).
            Pairs absent from a sparse matrix fall back to haversine
            per-cell at lookup time, by design.

    Returns:
        (minutes, flags): accepted cells and human-readable rejections.

    Raises:
        SystemExit: on a non-200 response — systemic refusal (API not enabled,
        key restriction, quota), not a per-cell miss.
    """
    # Each job is one request: (origin rows, destination rows).
    jobs: list[tuple[list[dict], list[dict]]] = []
    if nearest is None:
        origins_per_request = max(1, MAX_ELEMENTS_PER_REQUEST // len(places))
        for start in range(0, len(places), origins_per_request):
            end = start + origins_per_request
            jobs.append((places[start:end], places))
        expected = len(places) * (len(places) - 1)
    else:
        for origin in places:
            here = SimpleNamespace(lat=origin["lat"], lng=origin["lng"])
            neighbours = sorted(
                (p for p in places if p["id"] != origin["id"]),
                key=lambda p: haversine_km(here, SimpleNamespace(lat=p["lat"], lng=p["lng"])),
            )[:nearest]
            jobs.append(([origin], neighbours))
        expected = len(places) * min(nearest, len(places) - 1)

    minutes: dict[tuple[str, str], float] = {}
    flags: list[str] = []
    headers = {
        "X-Goog-Api-Key": key,
        "X-Goog-FieldMask": "originIndex,destinationIndex,duration,condition,status",
    }
    for origins, destinations in jobs:
        body = {
            "origins": [_waypoint(p) for p in origins],
            "destinations": [_waypoint(p) for p in destinations],
            "travelMode": mode,
            # Typical (non-live) times on purpose: this file must not be
            # secretly stamped with the traffic of the morning it was fetched.
            # Live traffic belongs to the per-request start legs, not here.
            "routingPreference": "TRAFFIC_UNAWARE",
        }
        response = client.post(MATRIX_URL, json=body, headers=headers)
        if response.status_code != 200:
            detail = response.json().get("error", {}).get("message", response.text[:200])
            sys.exit(f"Routes API refused (HTTP {response.status_code}): {detail}")
        for cell in response.json():
            # Indices are relative to this request's origin/destination lists.
            origin_id = origins[cell.get("originIndex", 0)]["id"]
            dest_id = destinations[cell.get("destinationIndex", 0)]["id"]
            if origin_id == dest_id:
                continue  # diagonal: place to itself (full-grid mode only)
            pair = f"{origin_id} → {dest_id}"
            if cell.get("condition") != "ROUTE_EXISTS" or "duration" not in cell:
                flags.append(f"{pair}: no route ({cell.get('condition', 'no condition')})")
                continue
            mins = int(cell["duration"].rstrip("s")) / 60.0
            if not MIN_PLAUSIBLE_MIN <= mins <= MAX_PLAUSIBLE_MIN:
                flags.append(f"{pair}: implausible {mins:.1f} min")
                continue
            minutes[(origin_id, dest_id)] = mins

    got = len(minutes) + len(flags)
    if got != expected:
        flags.append(f"MISSING CELLS: expected {expected}, received {got}")
    return minutes, flags


def print_report(
    minutes: dict[tuple[str, str], float], flags: list[str], *, places: list[dict[str, Any]]
) -> float:
    """Print the real-vs-estimate comparison and return the calibrated speed.

    Args:
        minutes: accepted real travel minutes per ordered pair.
        flags: rejected/missing-cell descriptions.
        places: seed rows, used to recompute the haversine baseline.

    Returns:
        The calibrated city speed in km/h (median implied speed over all
        pairs) — the evidence-based replacement for the CITY_SPEED_KMH guess.
    """
    coord = {p["id"]: SimpleNamespace(lat=p["lat"], lng=p["lng"]) for p in places}
    ratios: list[float] = []
    speeds: list[float] = []
    long_speeds: list[float] = []
    rows: list[tuple[float, str]] = []
    for (a, b), real_min in minutes.items():
        guess_min = travel_minutes(coord[a], coord[b])
        km = haversine_km(coord[a], coord[b])
        ratio = real_min / guess_min if guess_min > 0 else float("inf")
        ratios.append(ratio)
        if real_min > 0:
            speed = km / (real_min / 60.0)
            speeds.append(speed)
            if km >= CALIBRATION_MIN_KM:
                long_speeds.append(speed)
        rows.append((ratio, f"{a} → {b}: real {real_min:.1f} min vs guess {guess_min:.1f} min"))

    calibrated = median(long_speeds) if long_speeds else median(speeds)
    print(f"pairs accepted: {len(minutes)}   flagged: {len(flags)}")
    print(
        f"real vs {CITY_SPEED_KMH:g} km/h guess — "
        f"mean ratio {mean(ratios):.2f}×, median {median(ratios):.2f}×"
    )
    print(f"implied city speed (median, all pairs): {median(speeds):.1f} km/h")
    print(
        f"calibrated speed (pairs ≥ {CALIBRATION_MIN_KM:g} km, riding dominates): "
        f"{calibrated:.1f} km/h  (current guess: {CITY_SPEED_KMH:g})"
    )

    rows.sort(reverse=True)
    print("\nmost underestimated pairs (crow-flight lied the most):")
    for ratio, text in rows[:TOP_N]:
        print(f"  {ratio:.1f}×  {text}")

    asym: list[tuple[float, str]] = []
    for (a, b), ab in minutes.items():
        ba = minutes.get((b, a))
        if ba is not None and a < b:
            asym.append((abs(ab - ba), f"{a} ↔ {b}: {ab:.1f} vs {ba:.1f} min"))
    asym.sort(reverse=True)
    print("\nmost asymmetric pairs (one-way streets at work):")
    for diff, text in asym[:TOP_N]:
        print(f"  Δ{diff:.1f} min  {text}")

    if flags:
        print("\nflagged cells (left out of the matrix; runtime falls back to haversine):")
        for flag in flags:
            print(f"  {flag}")
    return calibrated


def main() -> None:
    """Fetch the matrix, print the comparison report, write only with --write."""
    parser = argparse.ArgumentParser(
        description="Build the place-to-place travel-time matrix (dry-run default)."
    )
    parser.add_argument(
        "--write", action="store_true", help="write pho_engine/data/travel_matrix.json"
    )
    parser.add_argument(
        "--mode", default=DEFAULT_MODE, help=f"Routes API travel mode (default {DEFAULT_MODE})"
    )
    parser.add_argument(
        "--nearest",
        type=int,
        default=None,
        help="sparse mode: fetch only each place's k nearest pairs (n·k elements, not n²)",
    )
    args = parser.parse_args()

    load_dotenv(_BACKEND_DIR / ".env")
    key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not key:
        sys.exit("GOOGLE_MAPS_API_KEY not set — create app/backend/.env (see .env.example).")

    places = json.loads(SEED_PATH.read_text(encoding="utf-8"))["places"]
    with httpx2.Client(timeout=30.0) as client:
        minutes, flags = fetch_matrix(
            client, places=places, mode=args.mode, key=key, nearest=args.nearest
        )
    calibrated = print_report(minutes, flags, places=places)

    if not args.write:
        print("\nDry run — nothing written. Re-run with --write to save the matrix.")
        return

    payload = {
        "_meta": {
            "mode": args.mode,
            "routing": "TRAFFIC_UNAWARE",
            "fetched": date.today().isoformat(),
            "places": len(places),
            "pairs": len(minutes),
            "nearest": args.nearest,
            "calibrated_speed_kmh": round(calibrated, 1),
            "calibration_min_km": CALIBRATION_MIN_KM,
        },
        "minutes": {f"{a}|{b}": round(m, 1) for (a, b), m in sorted(minutes.items())},
    }
    MATRIX_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"\nWrote {len(minutes)} pairs to {MATRIX_PATH.name}.")
    print(
        f"Calibrated fallback speed: {calibrated:.1f} km/h — update CITY_SPEED_KMH "
        "in pho_engine/distance.py (done by hand, reviewed like any code change)."
    )


if __name__ == "__main__":
    main()
