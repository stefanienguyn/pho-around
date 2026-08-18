"""Shared seed-file I/O for the one-time scripts (geocode, discover, …).

Reading is trivial; writing preserves the JSON's one-line-per-place layout so
git diffs show only the rows that actually changed — not a wholesale reformat.
Only scripts import this; the engine keeps its own loader (`pho_engine/seed.py`).
"""

from __future__ import annotations

import json
from pathlib import Path

SEED_PATH = Path(__file__).resolve().parents[1] / "pho_engine" / "data" / "seed_places.json"


def read_seed(*, path: Path | None = None) -> dict:
    """Load the raw seed JSON (note + places) as a plain dict."""
    return json.loads((path or SEED_PATH).read_text(encoding="utf-8"))


def write_seed(seed: dict, *, path: Path | None = None) -> None:
    """Write the seed JSON back, one place per line, Vietnamese kept readable.

    Args:
        seed: the full document ({"_note": ..., "places": [...]}).
        path: override the target (used by tests/dry experiments).
    """
    lines = ["{", f'  "_note": {json.dumps(seed["_note"], ensure_ascii=False)},', '  "places": [']
    last = len(seed["places"]) - 1
    for index, place in enumerate(seed["places"]):
        comma = "," if index < last else ""
        lines.append(f"    {json.dumps(place, ensure_ascii=False)}{comma}")
    lines += ["  ]", "}"]
    (path or SEED_PATH).write_text("\n".join(lines) + "\n", encoding="utf-8")
