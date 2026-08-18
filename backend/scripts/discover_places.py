"""Place discovery — the sanctioned "scrape" (phase 3½ era, file-era Rung A).

Asks the Places API Text Search for candidates ("museums in Hồ Chí Minh City"),
filters out places the seed already has, and prints a numbered menu. Writing
requires BOTH ``--accept`` (your picks) and ``--write``; accepted rows land in
``seed_places.json`` with category-default dwell/price, the Google rating as a
starting score, a ``needs-review`` tag, and — a first — their ``place_id``.

The menu is re-queried on every run, so between a dry run and an --accept run
the numbering can shift: always check the echoed names before trusting a write
(git diff remains the final gate). After writing: rebuild the travel matrix,
bump the count assertion in tests/test_seed.py, and curate the flagged fields.

    .venv/bin/python scripts/discover_places.py --query museum
    .venv/bin/python scripts/discover_places.py --query museum --accept 1,3 --write
"""

from __future__ import annotations

import argparse
import os
import sys
import unicodedata
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx2
from dotenv import load_dotenv

# Make pho_engine importable when run as a plain script from app/backend/.
_BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND_DIR))

from pho_engine.distance import haversine_km  # noqa: E402
from pho_engine.models import CATEGORIES  # noqa: E402
from seed_io import read_seed, write_seed  # noqa: E402

PLACES_URL = "https://places.googleapis.com/v1/places:searchText"
# Bias searches toward the city core (Bến Thành) so central results outrank
# far-flung namesakes; a bias, not a wall.
CITY_CENTER = SimpleNamespace(lat=10.7725, lng=106.6980)
BIAS_RADIUS_M = 6000.0
# Two records within this distance are the same building wearing two names.
DUP_RADIUS_KM = 0.1
# Judgement defaults per category (dwell minutes, price VND) — deliberately
# rough; every discovered row carries a needs-review tag until curated.
CATEGORY_DEFAULTS = {
    "food": (40, 60000),
    "coffee": (60, 55000),
    "dessert": (30, 35000),
    "shopping": (60, 0),
    "photobooth": (20, 100000),
    "landmark": (45, 0),
}
DEFAULT_SCORE = 4.0
# Sài Gòn districts that go by name, for address parsing.
NAMED_DISTRICTS = ["Phú Nhuận", "Bình Thạnh", "Tân Bình", "Gò Vấp", "Thủ Đức", "Bình Tân"]


def fold_ascii(name: str) -> str:
    """Fold a Vietnamese name into a plain-ASCII kebab id.

    NFD decomposition splits accented letters into base + combining marks,
    which are then dropped ("Bảo" → "Bao"). ``đ`` is its own letter — not an
    accented d — so it never decomposes and needs the explicit rule.
    """
    replaced = name.replace("đ", "d").replace("Đ", "D")
    decomposed = unicodedata.normalize("NFD", replaced)
    ascii_only = "".join(c for c in decomposed if not unicodedata.combining(c))
    kebab = "".join(c.lower() if c.isalnum() else "-" for c in ascii_only)
    return "-".join(part for part in kebab.split("-") if part)


def district_from_address(address: str) -> str:
    """Best-effort district from a formatted address; '' when unsure."""
    for n in range(1, 13):
        if f"District {n}" in address or f"Quận {n}" in address:
            return f"District {n}"
    for name in NAMED_DISTRICTS:
        if name in address:
            return name
    return ""


def search_places(client: httpx2.Client, *, query: str, limit: int, key: str) -> list[dict]:
    """Run one Text Search and return Google's candidate list.

    Raises:
        SystemExit: on a non-200 response (key/API/billing trouble) — quoting
        Google's own complaint, as this family of scripts always does.
    """
    body = {
        "textQuery": f"{query} in Hồ Chí Minh City",
        "pageSize": limit,
        "locationBias": {
            "circle": {
                "center": {"latitude": CITY_CENTER.lat, "longitude": CITY_CENTER.lng},
                "radius": BIAS_RADIUS_M,
            }
        },
    }
    headers = {
        "X-Goog-Api-Key": key,
        "X-Goog-FieldMask": (
            "places.id,places.displayName,places.formattedAddress,"
            "places.location,places.rating,places.userRatingCount,places.businessStatus"
        ),
    }
    response = client.post(PLACES_URL, json=body, headers=headers)
    if response.status_code != 200:
        detail = response.json().get("error", {}).get("message", response.text[:200])
        sys.exit(f"Places API refused (HTTP {response.status_code}): {detail}")
    return response.json().get("places", [])


def is_duplicate(candidate: dict, *, seed_places: list[dict[str, Any]]) -> bool:
    """True when the seed already holds this place (by id, distance, or name).

    Distance is the primary check: the same building often wears different
    names in Vietnamese and English, but it cannot stand somewhere else.
    """
    loc = candidate["location"]
    where = SimpleNamespace(lat=loc["latitude"], lng=loc["longitude"])
    folded = fold_ascii(candidate["displayName"]["text"])
    for row in seed_places:
        if row.get("place_id") == candidate["id"]:
            return True
        if haversine_km(where, SimpleNamespace(lat=row["lat"], lng=row["lng"])) < DUP_RADIUS_KM:
            return True
        if fold_ascii(row["name"]) == folded:
            return True
    return False


def print_menu(candidates: list[dict]) -> None:
    """Print the numbered candidate menu for the human to pick from."""
    for number, place in enumerate(candidates, start=1):
        loc = place["location"]
        km = haversine_km(CITY_CENTER, SimpleNamespace(lat=loc["latitude"], lng=loc["longitude"]))
        rating = place.get("rating")
        count = place.get("userRatingCount", 0)
        stars = f"{rating} ★ ({count:,})" if rating else "no rating"
        district = district_from_address(place.get("formattedAddress", "")) or "district?"
        print(f"{number:>3}. {place['displayName']['text']}")
        print(f"     {stars} · {district} · {km:.1f} km from Bến Thành")
        print(f"     {place.get('formattedAddress', '—')}")


def build_row(place: dict, *, category: str) -> dict[str, Any]:
    """Turn one accepted candidate into a seed row (defaults + needs-review)."""
    dwell, price = CATEGORY_DEFAULTS[category]
    loc = place["location"]
    return {
        "id": fold_ascii(place["displayName"]["text"]),
        "name": place["displayName"]["text"],
        "category": category,
        "district": district_from_address(place.get("formattedAddress", "")) or "Hồ Chí Minh City",
        "price_per_person_vnd": price,
        "avg_minutes": dwell,
        "score": round(place.get("rating", DEFAULT_SCORE), 1),
        "lat": round(loc["latitude"], 6),
        "lng": round(loc["longitude"], 6),
        "tags": ["needs-review"],
        "place_id": place["id"],
    }


def main() -> None:
    """Search, dedup, print the menu; append accepted rows only with --write."""
    parser = argparse.ArgumentParser(description="Discover candidate places (dry-run default).")
    parser.add_argument("--query", required=True, help='e.g. "museum", "temple"')
    parser.add_argument("--category", default="landmark", choices=sorted(CATEGORIES))
    parser.add_argument("--limit", type=int, default=10, help="menu size (default 10)")
    parser.add_argument("--accept", default="", help="menu numbers to accept, e.g. 1,3,7")
    parser.add_argument("--write", action="store_true", help="append accepted rows to the seed")
    args = parser.parse_args()

    load_dotenv(_BACKEND_DIR / ".env")
    key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not key:
        sys.exit("GOOGLE_MAPS_API_KEY not set — create app/backend/.env (see .env.example).")

    seed = read_seed()
    with httpx2.Client(timeout=15.0) as client:
        found = search_places(client, query=args.query, limit=args.limit, key=key)

    open_places = [p for p in found if p.get("businessStatus", "OPERATIONAL") == "OPERATIONAL"]
    candidates = [p for p in open_places if not is_duplicate(p, seed_places=seed["places"])]
    skipped = len(found) - len(candidates)
    print_menu(candidates)
    print(f"\n{len(candidates)} candidates ({skipped} skipped: already in seed or closed).")

    if not args.write:
        print("Dry run — nothing written. Pick with --accept 1,3,… and add --write.")
        return
    if not args.accept:
        sys.exit("--write needs --accept <numbers> — nothing was written.")

    numbers = [int(n) for n in args.accept.split(",") if n.strip()]
    bad = [n for n in numbers if not 1 <= n <= len(candidates)]
    if bad:
        sys.exit(f"--accept numbers out of range: {bad} (menu has {len(candidates)}).")

    rows = [build_row(candidates[n - 1], category=args.category) for n in numbers]
    seed["places"].extend(rows)
    write_seed(seed)
    print(f"\nWrote {len(rows)} new places ({len(seed['places'])} total):")
    for row in rows:
        print(f"  + {row['id']}  ({row['district']}, score {row['score']}, needs-review)")
    print(
        "\nNext: rebuild the travel matrix (build_travel_matrix.py --write), bump the "
        "count in tests/test_seed.py, curate the needs-review fields."
    )


if __name__ == "__main__":
    main()
