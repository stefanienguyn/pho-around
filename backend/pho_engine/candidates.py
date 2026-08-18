"""Candidate pre-filter: the solver's guest list.

At 100 seed places the MILP hit its scale wall (10 s solves, best-effort
answers). The fix is not a faster solver but a smaller, smarter instance:
each request pre-selects ~40 candidates — the nearest places to the start
(the clustering backbone of any itinerary) plus the best-scored of the rest
(guaranteed seats for destination-worthy places, whatever part of the city
they're in — the filter must never out-vote the local's taste).

The filter is start-relative on purpose: someone starting in Quận 7 gets
Quận 7 as their backbone and the city centre becomes their "far". Decided
with the human 2026-08-18; scale story in
``wiki_storage/wiki/concepts/itinerary-optimization.md``.
"""

from __future__ import annotations

from pho_engine.distance import HasCoords, haversine_km
from pho_engine.models import Place

# ~40 keeps CBC in its ~2-3 s comfort zone (measured: 100 places blew the
# 10 s cap; 37 solved in 2.3 s).
K_NEAREST = 30
K_BEST_FAR = 10


def select_candidates(
    places: list[Place], start: HasCoords, *, k_near: int = K_NEAREST, k_best: int = K_BEST_FAR
) -> list[Place]:
    """Pick the places one request's solver run will consider.

    Args:
        places: the full seed.
        start: the request's start point — nearness is relative to it.
        k_near: how many nearest places form the backbone.
        k_best: how many top-scored non-near places get guaranteed seats.

    Returns:
        At most ``k_near + k_best`` places, in original seed order (stable
        ordering keeps runs reproducible and tests deterministic).
    """
    if len(places) <= k_near + k_best:
        return list(places)
    by_distance = sorted(places, key=lambda p: haversine_km(start, p))
    near_ids = {p.id for p in by_distance[:k_near]}
    far_best = sorted(
        (p for p in places if p.id not in near_ids), key=lambda p: p.score, reverse=True
    )[:k_best]
    chosen = near_ids | {p.id for p in far_best}
    return [p for p in places if p.id in chosen]
