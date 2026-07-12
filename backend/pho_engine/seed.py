"""Load the hand-seeded Sài Gòn places into ``Place`` records.

The canonical human-readable dataset lives in ``wiki_storage/wiki/seed-places.md``;
``data/seed_places.json`` is its machine-readable copy. This module reads that JSON
and validates it against the schema in :mod:`pho_engine.models`.
"""

from __future__ import annotations

import json
from pathlib import Path

from pho_engine.models import CATEGORIES, Place

# The JSON sits next to this file, under data/. Resolved at import time so callers
# don't need to know where the package lives on disk.
_SEED_PATH = Path(__file__).parent / "data" / "seed_places.json"


def load_seed_places(*, path: Path | None = None) -> list[Place]:
    """Read the seed JSON and return validated ``Place`` records.

    Args:
        path: override the JSON location (used by tests). Defaults to the
            packaged ``data/seed_places.json``.

    Returns:
        The places in file order.

    Raises:
        ValueError: if any row has an unknown category or a score outside 0–5,
            so bad seed data fails loudly at load time rather than during solving.
    """
    source = path or _SEED_PATH
    raw = json.loads(source.read_text(encoding="utf-8"))

    places: list[Place] = []
    for row in raw["places"]:
        if row["category"] not in CATEGORIES:
            raise ValueError(f"{row['id']}: unknown category {row['category']!r}")
        if not 0.0 <= row["score"] <= 5.0:
            raise ValueError(f"{row['id']}: score {row['score']} outside 0–5")
        places.append(
            Place(
                id=row["id"],
                name=row["name"],
                category=row["category"],
                district=row["district"],
                price_per_person_vnd=row["price_per_person_vnd"],
                avg_minutes=row["avg_minutes"],
                score=row["score"],
                lat=row["lat"],
                lng=row["lng"],
                tags=tuple(row["tags"]),
            )
        )
    return places
