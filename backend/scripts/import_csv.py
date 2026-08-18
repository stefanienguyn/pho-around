"""CSV import — the human's curated food list, diffed against the seed.

Reads ``scripts/data/foodtour-food.csv`` (Shop Name, District, Type, Cuisine,
Address, Price/person), keeps only rows the seed doesn't already have, resolves
each survivor through Places Text Search (coords + place_id + rating), and
prints a numbered menu. Idempotent by design: re-run after every CSV update and
only the genuinely-new rows surface — that's the "spot the difference".

Chain policy (human's call, 2026-08-18): a known name at a NEW location is a
new row tagged "chain" (id auto-suffixed on collision); a known name within
100 m of an existing row is the same place and is skipped.

    .venv/bin/python scripts/import_csv.py                       # dry-run diff menu
    .venv/bin/python scripts/import_csv.py --accept 2,5 --write  # append picks
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx2
from dotenv import load_dotenv

# Make pho_engine (and sibling scripts) importable when run from app/backend/.
_BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND_DIR))
sys.path.insert(0, str(_BACKEND_DIR / "scripts"))

from pho_engine.distance import haversine_km  # noqa: E402
from discover_places import CATEGORY_DEFAULTS, CITY_CENTER, DUP_RADIUS_KM, fold_ascii  # noqa: E402
from geocode_seed import LAT_BOUNDS, LNG_BOUNDS  # noqa: E402
from seed_io import read_seed, write_seed  # noqa: E402

CSV_PATH = _BACKEND_DIR / "scripts" / "data" / "foodtour-food.csv"
PLACES_URL = "https://places.googleapis.com/v1/places:searchText"
# The CSV spans the whole city (D7, D11, Thảo Điền…) — bias wide, not tight.
CITY_BIAS_RADIUS_M = 15000.0
DEFAULT_SCORE = 4.0

# CSV "Type" column → our categories.
TYPE_TO_CATEGORY = {
    "Main meal": "food",
    "Snacks": "food",
    "Cafe": "coffee",
    "Dessert/Sweets": "dessert",
}
# CSV price ranges → a usable VND number (midpoint; open ends nudged inward).
PRICE_RANGES = {
    "< 60.000đ": 45000,
    "60.000đ-100.000đ": 80000,
    "100.000đ-200.000đ": 150000,
    "200.000đ-300.000đ": 250000,
    "300.000đ-500.000đ": 400000,
    ">500.000đ": 600000,
}


def resolve_place(client: httpx2.Client, *, row: dict[str, str], key: str) -> dict | None:
    """Find one CSV row on Google: coords, place_id, rating.

    Queries name + address together: alone, an address-only Address column
    resolves to the street itself (no business, no rating — and once 62 km
    away on a namesake street). Returns None on no match or a result outside
    the Sài Gòn sanity box.

    Raises:
        SystemExit: on a non-200 response (systemic refusal), as always.
    """
    name = row["Shop Name"].strip()
    address = row["Address"].strip()
    query = name if not address or address == name else f"{name}, {address}"
    body = {
        "textQuery": f"{query}, Hồ Chí Minh City",
        "pageSize": 1,
        "locationBias": {
            "circle": {
                "center": {"latitude": CITY_CENTER.lat, "longitude": CITY_CENTER.lng},
                "radius": CITY_BIAS_RADIUS_M,
            }
        },
    }
    headers = {
        "X-Goog-Api-Key": key,
        "X-Goog-FieldMask": (
            "places.id,places.displayName,places.location,"
            "places.rating,places.userRatingCount,places.businessStatus"
        ),
    }
    response = client.post(PLACES_URL, json=body, headers=headers)
    if response.status_code != 200:
        detail = response.json().get("error", {}).get("message", response.text[:200])
        sys.exit(f"Places API refused (HTTP {response.status_code}): {detail}")
    places = response.json().get("places", [])
    if not places:
        return None
    loc = places[0]["location"]
    if not (
        LAT_BOUNDS[0] < loc["latitude"] < LAT_BOUNDS[1]
        and LNG_BOUNDS[0] < loc["longitude"] < LNG_BOUNDS[1]
    ):
        return None  # a namesake outside Sài Gòn — no guess beats a wrong one
    return places[0]


def classify(resolved: dict, *, row: dict[str, str], seed_places: list[dict]) -> str:
    """DUPLICATE (same branch / known id), CHAIN (known name, new spot), or NEW."""
    loc = resolved["location"]
    where = SimpleNamespace(lat=loc["latitude"], lng=loc["longitude"])
    folded = fold_ascii(row["Shop Name"])
    name_known = False
    for existing in seed_places:
        if existing.get("place_id") == resolved["id"]:
            return "DUPLICATE"
        near = haversine_km(where, SimpleNamespace(lat=existing["lat"], lng=existing["lng"]))
        same_name = fold_ascii(existing["name"]) == folded
        if near < DUP_RADIUS_KM:
            return "DUPLICATE"
        if same_name:
            name_known = True
    return "CHAIN" if name_known else "NEW"


def unique_id(base: str, *, seed_places: list[dict], pending: list[dict]) -> str:
    """The folded id, numerically suffixed if a row (old or pending) holds it."""
    taken = {p["id"] for p in seed_places} | {p["id"] for p in pending}
    candidate, n = base, 1
    while candidate in taken:
        n += 1
        candidate = f"{base}-{n}"
    return candidate


def build_row(
    resolved: dict,
    *,
    row: dict[str, str],
    status: str,
    seed_places: list[dict],
    pending: list[dict],
) -> dict[str, Any]:
    """Turn a CSV row + its Google resolution into a seed row.

    Judgement fields come from the HUMAN's data wherever it exists: the name
    is the CSV's (curation over Google's registry), the price is the CSV
    range's midpoint. Google supplies facts: coords, place_id, rating. Dwell
    is a category default → the row keeps a needs-review tag.
    """
    category = TYPE_TO_CATEGORY[row["Type"].strip()]
    dwell, _ = CATEGORY_DEFAULTS[category]
    loc = resolved["location"]
    tags = []
    cuisine = row["Cuisine"].strip()
    if cuisine and cuisine != "N/A":
        tags.append(cuisine.lower())
    if status == "CHAIN":
        tags.append("chain")
    tags.append("needs-review")
    return {
        "id": unique_id(fold_ascii(row["Shop Name"]), seed_places=seed_places, pending=pending),
        "name": row["Shop Name"].strip(),
        "category": category,
        "district": row["District"].strip() or "Hồ Chí Minh City",
        "price_per_person_vnd": PRICE_RANGES[row["Price/person"].strip()],
        "avg_minutes": dwell,
        "score": round(resolved.get("rating", DEFAULT_SCORE), 1),
        "lat": round(loc["latitude"], 6),
        "lng": round(loc["longitude"], 6),
        "tags": tags,
        "place_id": resolved["id"],
    }


def main() -> None:
    """Diff the CSV against the seed; menu the new rows; write only picks."""
    parser = argparse.ArgumentParser(description="Import the human's CSV (dry-run default).")
    parser.add_argument("--csv", type=Path, default=CSV_PATH, help="CSV to import")
    parser.add_argument("--accept", default="", help="menu numbers to accept, e.g. 2,5,9")
    parser.add_argument("--write", action="store_true", help="append accepted rows to the seed")
    args = parser.parse_args()

    load_dotenv(_BACKEND_DIR / ".env")
    key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not key:
        sys.exit("GOOGLE_MAPS_API_KEY not set — create app/backend/.env (see .env.example).")

    with args.csv.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    seed = read_seed()

    menu: list[tuple[dict, dict, str]] = []  # (csv_row, resolved, status) for NEW/CHAIN
    dup_count = unresolved = 0
    with httpx2.Client(timeout=15.0) as client:
        for row in rows:
            resolved = resolve_place(client, row=row, key=key)
            if resolved is None or resolved.get("businessStatus", "OPERATIONAL") != "OPERATIONAL":
                unresolved += 1
                print(f"  ?  {row['Shop Name']}: no confident match — left out")
                continue
            status = classify(resolved, row=row, seed_places=seed["places"])
            if status == "DUPLICATE":
                dup_count += 1
                continue
            menu.append((row, resolved, status))

    print(
        f"\n{len(rows)} CSV rows → {len(menu)} new, {dup_count} already in seed, "
        f"{unresolved} unresolved.\n"
    )
    for number, (row, resolved, status) in enumerate(menu, start=1):
        google_name = resolved["displayName"]["text"]
        rating = resolved.get("rating")
        stars = f"{rating} ★ ({resolved.get('userRatingCount', 0):,})" if rating else "no rating"
        loc = resolved["location"]
        km = haversine_km(CITY_CENTER, SimpleNamespace(lat=loc["latitude"], lng=loc["longitude"]))
        chain = " · CHAIN branch" if status == "CHAIN" else ""
        print(f"{number:>3}. {row['Shop Name']}  ({row['Type']} · {row['Price/person']}){chain}")
        print(f"     Google: {google_name} · {stars} · {km:.1f} km from Bến Thành")

    if not args.write:
        print("\nDry run — nothing written. Pick with --accept 2,5,… and add --write.")
        return
    if not args.accept:
        sys.exit("--write needs --accept <numbers> — nothing was written.")

    numbers = [int(n) for n in args.accept.split(",") if n.strip()]
    bad = [n for n in numbers if not 1 <= n <= len(menu)]
    if bad:
        sys.exit(f"--accept numbers out of range: {bad} (menu has {len(menu)}).")

    pending: list[dict] = []
    for n in numbers:
        row, resolved, status = menu[n - 1]
        pending.append(
            build_row(resolved, row=row, status=status, seed_places=seed["places"], pending=pending)
        )
    seed["places"].extend(pending)
    write_seed(seed)
    print(f"\nWrote {len(pending)} new places ({len(seed['places'])} total):")
    for built in pending:
        print(
            f"  + {built['id']}  ({built['category']}, {built['price_per_person_vnd']:,} ₫, "
            f"score {built['score']})"
        )
    print(
        "\nNext: rebuild the travel matrix (build_travel_matrix.py --write), bump the "
        "count in tests/test_seed.py, curate the needs-review dwell times."
    )


if __name__ == "__main__":
    main()
