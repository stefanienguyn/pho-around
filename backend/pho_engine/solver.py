"""The OR/LP itinerary engine — the app's differentiator.

Given a start location, a time budget and a money budget, choose a subset of
places and order them into a single open route that maximises total appeal.
This is the *orienteering problem* (prize-collecting TSP with a budget);
the plain-terms model lives in
``wiki_storage/wiki/concepts/itinerary-optimization.md``.

The whole thing is a pure function: places + constraints in, an ``Itinerary``
out. No I/O, no globals — so it is unit-testable in isolation (phase 2).

## The MILP, in one place

Nodes: the depot (the user's start) is node 0; the candidate places are 1..n.

Decision variables
  * ``visit[i]`` in {0,1}  — do we include place i?
  * ``go[i][j]`` in {0,1}  — do we travel directly from i to j? Edges exist only
    *out of the depot* and *between places*, never back into the depot — that is
    what makes the route an open path (start fixed, end free).
  * ``u[i]`` in [1,n]      — MTZ ordering position of place i, used only to forbid
    disconnected sub-loops.

Objective (maximise)   sum score[i]*visit[i]

Constraints
  * money    sum price[i]*visit[i]                          <= money_budget
  * time     sum dwell[i]*visit[i] + sum travel[i][j]*go[i][j] <= time_budget
  * start    the depot is left at most once
  * in-deg   every place is entered exactly once iff visited
  * out-deg  every place is left at most once, and only if visited
  * MTZ      no subtour among places (the route is one chain from the depot)
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence

import pulp

from pho_engine.constraints import Constraint, apply_constraints
from pho_engine.distance import CITY_SPEED_KMH, travel_minutes
from pho_engine.travel import TravelTimeFn
from pho_engine.models import Itinerary, Place, Start, Stop

# Default ceiling on solve time so a pathological instance can't hang a caller.
# The v1 seed (~30 places) solves in a couple of seconds; this is just a guard.
_DEFAULT_TIME_LIMIT_S = 10

# CBC parallelism. Branch-and-bound over the MTZ formulation is the slow part;
# a handful of threads roughly halves wall time on the seed. Capped at 4 because
# more oversubscribes and stops helping (measured), and floored by the machine's
# core count so small boxes don't oversubscribe.
_SOLVER_THREADS = min(4, os.cpu_count() or 1)

# Safety margin for the travel tiebreaker (see _travel_penalty_weight).
_TIEBREAK_SAFETY = 10.0

# Real-world friction per stop, in minutes: finding the door, parking, queueing,
# ordering, paying. `avg_minutes` only covers time *inside* the place, so without
# this the engine plans a day with zero slack (the 30-place seed packed 239.3 of
# 240 minutes). The cost scales with the number of stops, which is what keeps the
# optimiser from cramming in one more place.
STOP_BUFFER_MIN = 5.0

# Appeal charged per repeat visit to a category, beyond the first. Variety is a
# *universal* preference, so it lives in the objective permanently rather than in
# a constraint every user has to ask for.
#
# The rate is per category because **satiation is**: two landmarks back to back
# are a fine afternoon (sightseeing scales), while a second coffee is a bad idea
# however many stops separate it from the first (caffeine doesn't care about
# distance). Note food is deliberately cheap — a multi-stop eating crawl is the
# app's whole point, not a defect.
#
# All soft, never caps: against scores in the 4.0-4.9 band a repeat still wins if
# it is genuinely better than the best alternative by more than its rate.
VARIETY_PENALTIES = {
    "food": 0.2,
    "coffee": 1.0,
    "dessert": 0.6,
    "shopping": 0.8,
    "photobooth": 1.5,
    "landmark": 0.2,
}


def _travel_penalty_weight(
    *, scores: list[float], time_budget_min: float, variety_penalties: Sequence[float] = ()
) -> float:
    """Weight (epsilon) for the travel-time tiebreaker in the objective.

    Why a tiebreaker at all: the objective only rewards the *score* of visited
    places, so two routes over the same places score identically no matter how
    much backtracking they involve. With a loose time budget the solver has no
    reason to prefer the short route and will happily return a zigzag. Adding
    ``- epsilon * (total travel)`` breaks those ties toward the shorter route.

    Why epsilon must be *small*: the penalty must never overturn a real score
    difference — it may only break exact ties. This makes the objective
    *lexicographic*: maximise score first, then minimise travel among the
    score-optimal plans.

    Sizing it. Total travel in any feasible route is bounded by the time budget T
    (travel alone cannot exceed it), so the entire penalty is at most epsilon*T.
    For the penalty to be unable to overturn any genuine score gap, we need

        epsilon * T  <  the smallest score difference the solver could trade away

    Two ways a plan's score can change, so delta is the smaller of:
      * **dropping** a place — costs at least the smallest score, and
      * **swapping** one place for another — costs at least the smallest gap
        between two distinct scores (e.g. 0.1 for our 4.2-vs-4.3 seed ratings).

    Sizing against the smallest *score* alone is the bug this replaces: with
    scores of 4.0-4.5, a max penalty of 0.4 could not drop a place (4.0) but could
    happily swap a far 4.3 for a near 4.2. Bounding by the smallest *gap* (0.1)
    closes that, with SAFETY as the margin.

    **Takes scores, not places, on purpose.** Category boosts multiply a place's
    score, and the *effective* (post-weight) scores are what the objective
    actually trades in. Sizing epsilon from raw scores while optimising weighted
    ones re-opens the swap bug above: a raw 4.4 against a boosted 3.5*1.25=4.375
    is a gap of 0.025, four times tighter than the raw seed's 0.1.

    The variety penalty widens the space of achievable objective differences the
    same way — a score gap can be partially cancelled by lambda — so it joins the
    candidate magnitudes below. Exhaustively enumerating every reachable
    difference is a number-theory problem; SAFETY is the margin that covers what
    this approximation misses, and the two regression tests are the tripwire.

    Args:
        scores: the effective (post-weight) scores of the candidate places.
        time_budget_min: the time budget T, which bounds total travel.
        variety_penalties: the distinct per-category repeat penalties in play.

    Returns:
        The epsilon weight, or 0.0 when no safe positive value exists (e.g. a
        zero/negative budget, or no place with a positive score) — in which case
        the objective falls back to pure score maximisation.
    """
    distinct = sorted({score for score in scores if score > 0})
    if not distinct or time_budget_min <= 0:
        return 0.0
    # Smallest score a plan could lose by dropping a place...
    smallest_score = distinct[0]
    # ...and smallest it could lose by swapping one place for a slightly worse one.
    gaps = [hi - lo for lo, hi in zip(distinct, distinct[1:])]
    magnitudes = [smallest_score, *gaps]
    for penalty in {p for p in variety_penalties if p > 0}:
        # A repeat costs its category's penalty, and a swap that also changes a
        # category count trades a score gap against that penalty — both are
        # objective differences epsilon must stay under.
        magnitudes.append(penalty)
        magnitudes.extend(abs(gap - penalty) for gap in gaps)
    delta = min(magnitude for magnitude in magnitudes if magnitude > 0)
    return delta / (time_budget_min * _TIEBREAK_SAFETY)


def plan_itinerary(
    places: list[Place],
    start: Start,
    *,
    time_budget_min: float,
    money_budget_vnd: int,
    speed_kmh: float = CITY_SPEED_KMH,
    stop_buffer_min: float = STOP_BUFFER_MIN,
    time_limit_s: int = _DEFAULT_TIME_LIMIT_S,
    travel_time_fn: TravelTimeFn | None = None,
    constraints: Sequence[Constraint] = (),
    variety_penalties: Mapping[str, float] = VARIETY_PENALTIES,
) -> Itinerary:
    """Compute the highest-value itinerary that fits the time and money budgets.

    Args:
        places: candidate places (each needs coords, dwell, price, score).
        start: the user's starting location (the route's depot).
        time_budget_min: total minutes available (dwell + buffer + travel).
        money_budget_vnd: total spend allowed, in VND.
        speed_kmh: assumed travel speed for the haversine time estimate.
            Ignored when ``travel_time_fn`` is provided.
        travel_time_fn: optional injected answerer for "minutes from a to b"
            (see :mod:`pho_engine.travel`). Default None keeps the haversine
            estimate — existing callers and tests are unaffected.
        stop_buffer_min: real-world friction added to every stop's dwell time
            (see :data:`STOP_BUFFER_MIN`). Pass 0 to model dwell time exactly.
        time_limit_s: solver wall-clock cap; a safety guard, not a tuning knob.
        constraints: optional preference vocabulary (see
            :mod:`pho_engine.constraints`) — boosts reweight scores, exclusions
            filter the pool, the rest become side constraints. Empty by
            default, which reproduces the pre-constraint behaviour exactly.
        variety_penalties: category → appeal charged per repeat visit (see
            :data:`VARIETY_PENALTIES`). Categories absent from the mapping are
            free to repeat; pass ``{}`` to disable variety entirely.

    Returns:
        An ``Itinerary``. If nothing fits the budgets, ``stops`` is empty — a
        valid answer, not an error. ``total_minutes`` includes the buffer, so it
        is what the plan really costs. ``total_score`` reports **raw** appeal:
        weights are a per-request lens, so a weighted total would inflate the
        number and make two plans incomparable.

    Raises:
        ValueError: if a required place is absent from ``places``. Pinning
            ``visit[i] = 1`` on a place that never became a variable is
            infeasible by construction, so the caller must include required
            places in the candidate set (see :func:`candidates.select_candidates`).
    """
    # Hard filters first: excluded places never become variables at all, which
    # also shrinks the n^2 MTZ block. Idempotent — on the API path the pool was
    # already filtered before candidate pre-selection, so this pass is a no-op.
    applied = apply_constraints(places, constraints=constraints)
    places = applied.pool
    n = len(places)
    if n == 0:
        return Itinerary(stops=(), total_score=0.0, total_minutes=0.0, total_cost_vnd=0)

    missing_required = applied.required_ids - {place.id for place in places}
    if missing_required:
        raise ValueError(
            "required places absent from the candidate set: " f"{sorted(missing_required)}"
        )

    # Node 0 is the depot; places are 1..n. `coord_of` maps every node index to
    # something with lat/lng (the Start for 0, a Place otherwise).
    place_idx = range(1, n + 1)
    # What the objective trades in: appeal as seen through this request's taste.
    # `total_score` still reports raw appeal (see the docstring).
    effective_score = [place.score * applied.weights[place.id] for place in places]
    coord_of: dict[int, Start | Place] = {0: start, **{i: places[i - 1] for i in place_idx}}

    # Precompute travel minutes for every edge we will create: depot->place and
    # place->place. No edge returns to the depot (open path), so no *->0 entries.
    # The answers come from the injected travel_time_fn when one is provided
    # (real matrix + live legs), else from the haversine estimate as before.
    fn = travel_time_fn or (lambda a, b: travel_minutes(a, b, speed_kmh=speed_kmh))
    travel: dict[tuple[int, int], float] = {}
    for i in [0, *place_idx]:
        for j in place_idx:
            if i != j:
                travel[(i, j)] = fn(coord_of[i], coord_of[j])

    prob = pulp.LpProblem("itinerary", pulp.LpMaximize)

    # --- Decision variables -------------------------------------------------
    visit = {i: pulp.LpVariable(f"visit_{i}", cat="Binary") for i in place_idx}
    go = {edge: pulp.LpVariable(f"go_{edge[0]}_{edge[1]}", cat="Binary") for edge in travel}
    # MTZ position variables, one per place, continuous in [1, n].
    u = {i: pulp.LpVariable(f"u_{i}", lowBound=1, upBound=n) for i in place_idx}
    # Variety: one continuous "extra visits" variable per category. Because the
    # objective is maximised and the penalty is positive, the solver drives each
    # down to its lower bound, so extra[c] settles at exactly max(0, count - 1) —
    # a diminishing-returns shape with no binaries and no branching cost.
    by_category: dict[str, list[int]] = {}
    for i in place_idx:
        by_category.setdefault(places[i - 1].category, []).append(i)
    extra = {category: pulp.LpVariable(f"extra_{category}", lowBound=0) for category in by_category}

    # --- Objective: maximise total appeal, minus a tiny travel tiebreaker ---
    # The score term is what we actually optimise. The epsilon*travel term only
    # breaks ties between routes that visit the same places, steering the solver
    # to the shorter one instead of an arbitrary zigzag. Epsilon is sized so it
    # can never justify dropping a place (see _travel_penalty_weight).
    epsilon = _travel_penalty_weight(
        scores=effective_score,
        time_budget_min=time_budget_min,
        variety_penalties=[variety_penalties.get(category, 0.0) for category in by_category],
    )
    prob += (
        pulp.lpSum(effective_score[i - 1] * visit[i] for i in place_idx)
        - pulp.lpSum(
            variety_penalties.get(category, 0.0) * extra[category] for category in by_category
        )
        - epsilon * pulp.lpSum(travel[e] * go[e] for e in travel)
    )

    # --- Budget constraints -------------------------------------------------
    # Money: sum of price-per-person over chosen places.
    prob += (
        pulp.lpSum(places[i - 1].price_per_person_vnd * visit[i] for i in place_idx)
        <= money_budget_vnd
    ), "money_budget"
    # Time: (dwell + per-stop buffer) at chosen places + travel along chosen edges.
    # The buffer rides on the dwell coefficient, so the constraint stays linear.
    prob += (
        pulp.lpSum((places[i - 1].avg_minutes + stop_buffer_min) * visit[i] for i in place_idx)
        + pulp.lpSum(travel[e] * go[e] for e in travel)
        <= time_budget_min
    ), "time_budget"

    # --- Variety + requested side constraints -------------------------------
    # Link each category's "extra visits" variable to its visit count.
    for category, members in by_category.items():
        prob += (
            extra[category] >= pulp.lpSum(visit[i] for i in members) - 1
        ), f"variety_{category}"

    # The hard half of the constraint vocabulary — one linear line each.
    index_of = {place.id: i for i, place in enumerate(places, start=1)}
    for place_id in sorted(applied.required_ids):
        prob += visit[index_of[place_id]] == 1, f"require_{place_id}"
    for category, count in sorted(applied.min_category.items()):
        members = by_category.get(category, [])
        prob += pulp.lpSum(visit[i] for i in members) >= count, f"min_{category}"
    for category, count in sorted(applied.max_category.items()):
        members = by_category.get(category, [])
        prob += pulp.lpSum(visit[i] for i in members) <= count, f"max_{category}"
    if applied.max_stops is not None:
        prob += pulp.lpSum(visit.values()) <= applied.max_stops, "max_stops"
    # The first stop is whichever place the depot's single outgoing arc enters,
    # so "start with X" is a constraint on that arc — not on the MTZ positions,
    # which are continuous and only forbid subtours, never exact ranks. Forcing
    # go[0→X] = 1 also forces visit[X] = 1 through X's in-degree equation.
    for place_id in sorted(applied.first_ids):
        prob += go[(0, index_of[place_id])] == 1, f"first_{place_id}"
    for category in sorted(applied.first_categories):
        members = by_category.get(category, [])
        prob += pulp.lpSum(go[(0, i)] for i in members) == 1, f"first_{category}"

    # --- Route-structure constraints ---------------------------------------
    # Start: the depot is left at most once (zero if we visit nothing).
    prob += pulp.lpSum(go[(0, j)] for j in place_idx) <= 1, "depot_out"

    for k in place_idx:
        # In-degree: a place is entered exactly once iff it is visited. The edge
        # may come from the depot or from another place.
        prob += (
            pulp.lpSum(go[(i, k)] for i in [0, *place_idx] if (i, k) in travel) == visit[k]
        ), f"in_degree_{k}"
        # Out-degree: a place is left at most once, and only if visited. Exactly
        # one visited place (the last stop) is left zero times — that ends the path.
        prob += (
            pulp.lpSum(go[(k, j)] for j in place_idx if (k, j) in travel) <= visit[k]
        ), f"out_degree_{k}"

    # MTZ subtour elimination: if we travel i->j then j must come later in order
    # (u[j] >= u[i] + 1). A place-only cycle would need a position smaller than
    # itself, which is impossible, so the only surviving shape is one chain
    # rooted at the depot. When go[i][j]=0 the constraint is slack (always true).
    for i in place_idx:
        for j in place_idx:
            if i != j:
                prob += u[i] - u[j] + n * go[(i, j)] <= n - 1, f"mtz_{i}_{j}"

    # --- Solve --------------------------------------------------------------
    prob.solve(pulp.PULP_CBC_CMD(msg=0, timeLimit=time_limit_s, threads=_SOLVER_THREADS))

    return _extract_itinerary(
        prob=prob, places=places, go=go, travel=travel, stop_buffer_min=stop_buffer_min
    )


def _extract_itinerary(
    *,
    prob: pulp.LpProblem,
    places: list[Place],
    go: dict[tuple[int, int], pulp.LpVariable],
    travel: dict[tuple[int, int], float],
    stop_buffer_min: float,
) -> Itinerary:
    """Turn a solved MILP into an ordered ``Itinerary`` by walking the edges.

    Follows the single chosen edge out of the depot, then hops place->place until
    a stop with no outgoing edge (the end of the open path). Returns an empty
    itinerary if the solver found no feasible/optimal route.

    ``total_minutes`` charges the same per-stop buffer the time constraint did, so
    the reported cost matches what was actually budgeted.
    """
    # "Optimal" means CBC proved no better route exists. "Not Solved" is what it
    # reports when the time limit stopped the search — but the incumbent it holds
    # is still a *feasible* integer solution: branch and bound loses the
    # optimality proof, never the budget guarantees. Returning that slightly
    # unproven plan beats returning nothing.
    #
    # Found on Render's 0.1-CPU free tier, where a 4-hour query exceeds the cap:
    # the API answered "nothing fits your budgets" while holding a route scoring
    # 27.7. Note PuLP's own ``sol_status`` says "No Solution Found" here, so the
    # populated objective is the honest signal.
    if pulp.LpStatus[prob.status] not in ("Optimal", "Not Solved"):
        return Itinerary(stops=(), total_score=0.0, total_minutes=0.0, total_cost_vnd=0)
    if pulp.value(prob.objective) is None:
        return Itinerary(stops=(), total_score=0.0, total_minutes=0.0, total_cost_vnd=0)

    # Map each used edge tail->head. Values are 0/1 when a solution exists and
    # None when the search found nothing at all, hence the `or 0`.
    next_of = {i: j for (i, j) in travel if (pulp.value(go[(i, j)]) or 0) > 0.5}

    stops: list[Stop] = []
    total_score = 0.0
    total_cost = 0
    total_minutes = 0.0
    current = 0  # start at the depot
    order = 0
    while current in next_of:
        nxt = next_of[current]
        place = places[nxt - 1]
        order += 1
        leg = travel[(current, nxt)]
        stops.append(Stop(order=order, place=place, travel_minutes_from_prev=leg))
        total_score += place.score
        total_cost += place.price_per_person_vnd
        total_minutes += place.avg_minutes + stop_buffer_min + leg
        current = nxt

    return Itinerary(
        stops=tuple(stops),
        total_score=round(total_score, 6),
        total_minutes=round(total_minutes, 6),
        total_cost_vnd=total_cost,
    )
