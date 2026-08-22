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

from collections.abc import Iterable

from pho_engine.distance import HasCoords, haversine_km
from pho_engine.models import Place

# 25 candidates, measured across five start/budget scenarios (2026-08-18).
#
# The first cut was 40, chosen when 100 places blew the solver's 10 s cap. Real
# deployment disproved it: on a 0.1-CPU instance a 40-candidate instance either
# times out with a poor plan or — for District 7 and District 3 starts — fails
# to find *any* feasible solution before the cap, i.e. an empty plan for the
# user. Measured under equivalent CPU pressure:
#
#   pool 40 → 17.6 appeal (D1 4h) and 0.0 (D7, D3): unusable
#   pool 30 → worst case 86.7% of its own best
#   pool 25 → worst case 98.7% of its own best, and beat pool 30 in absolute
#             appeal in every pressured scenario
#
# Unlimited CPU slightly favours bigger pools (a wider net can score higher),
# but that ceiling is unreachable on modest hardware — so the default is the
# number that *delivers*, not the one that looks best on a fast laptop. Raise
# `k_near`/`k_best` per call if the deployment ever gets real CPU.
K_NEAREST = 18
K_BEST_FAR = 7


def select_candidates(
    places: list[Place],
    start: HasCoords,
    *,
    k_near: int = K_NEAREST,
    k_best: int = K_BEST_FAR,
    must_include: Iterable[str] = (),
) -> list[Place]:
    """Pick the places one request's solver run will consider.

    Args:
        places: the full seed.
        start: the request's start point — nearness is relative to it.
        k_near: how many nearest places form the backbone.
        k_best: how many top-scored non-near places get guaranteed seats.
        must_include: place ids that must survive whatever the distance and
            score doors decide — required places (``RequirePlace``). Without
            this a required place could be filtered out and then pinned with
            ``visit[i] = 1`` while absent from the model, which is infeasible
            by construction.

    Returns:
        At most ``k_near + k_best`` places plus any forced ones, in original
        seed order (stable ordering keeps runs reproducible and tests
        deterministic).
    """
    forced = set(must_include)
    if len(places) <= k_near + k_best:
        return list(places)
    by_distance = sorted(places, key=lambda p: haversine_km(start, p))
    near_ids = {p.id for p in by_distance[:k_near]}
    far_best = sorted(
        (p for p in places if p.id not in near_ids), key=lambda p: p.score, reverse=True
    )[:k_best]
    chosen = near_ids | {p.id for p in far_best} | forced
    return [p for p in places if p.id in chosen]
