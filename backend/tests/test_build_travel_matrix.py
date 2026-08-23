"""Tests for the travel-matrix builder's incremental fetch planning.

Pure planning logic, no network: these pin the money-saving behaviour, since
every Routes element is billed and the August 2026 bill ($106.01 for 8,067
elements) came from refetching pairs we already owned.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_travel_matrix import plan_fetch, wanted_pairs  # noqa: E402


def make_place(id: str, *, lat: float, lng: float) -> dict:
    """A seed row with only the fields the planner reads."""
    return {"id": id, "lat": lat, "lng": lng}


# Five places strung west to east, ~110 m apart, so "nearest" is unambiguous.
PLACES = [make_place(f"p{i}", lat=10.78, lng=106.70 + i * 0.001) for i in range(5)]


def test_wanted_pairs_covers_every_ordered_pair_when_dense() -> None:
    """Without a nearest limit, every ordered pair is wanted (n*(n-1))."""
    pairs = wanted_pairs(PLACES, nearest=None)
    assert len(pairs) == 5 * 4
    assert ("p0", "p4") in pairs and ("p4", "p0") in pairs
    assert ("p0", "p0") not in pairs, "no place travels to itself"


def test_wanted_pairs_is_capped_by_nearest() -> None:
    """With k=2, each place wants exactly its two closest neighbours."""
    pairs = wanted_pairs(PLACES, nearest=2)
    assert len(pairs) == 5 * 2
    # p0's neighbours are p1 and p2; p4 is far and must not be wanted.
    assert {dest for origin, dest in pairs if origin == "p0"} == {"p1", "p2"}


def test_a_rerun_with_nothing_new_fetches_nothing() -> None:
    """The headline property: rebuilding an unchanged dataset is free.

    Before this, `build_travel_matrix.py --write` refetched the whole table
    every time — about $26 at 100 places, whether or not anything changed.
    """
    wanted = wanted_pairs(PLACES, nearest=2)
    known = {pair: 5.0 for pair in wanted}
    jobs, to_fetch = plan_fetch(PLACES, wanted=wanted, known=known)
    assert to_fetch == 0
    assert jobs == []


def test_adding_one_place_fetches_only_the_pairs_it_introduces() -> None:
    """Adding a place buys its own rows plus the rows that now point at it."""
    wanted_before = wanted_pairs(PLACES, nearest=2)
    known = {pair: 5.0 for pair in wanted_before}

    grown = [*PLACES, make_place("new", lat=10.78, lng=106.7005)]
    wanted_after = wanted_pairs(grown, nearest=2)
    _, to_fetch = plan_fetch(grown, wanted=wanted_after, known=known)

    # Only genuinely-new pairs are bought, and nothing already held is re-bought.
    assert to_fetch == len(wanted_after - set(known))
    assert to_fetch < len(wanted_after), "a full refetch would defeat the point"
    # Every fetched pair involves the newcomer, directly or by displacing it
    # into an existing place's neighbour list.
    assert all("new" in pair for pair in wanted_after - set(known))


def test_partial_knowledge_only_fills_the_gaps() -> None:
    """Half a matrix on disk means half a matrix to buy."""
    wanted = wanted_pairs(PLACES, nearest=2)
    half = dict.fromkeys(sorted(wanted)[: len(wanted) // 2], 5.0)
    _, to_fetch = plan_fetch(PLACES, wanted=wanted, known=half)
    assert to_fetch == len(wanted) - len(half)
