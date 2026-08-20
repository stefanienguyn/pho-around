"""The constraint vocabulary — the only surface an outside caller may touch.

A closed, typed set of seven "forms". Callers (today the API, later an LLM
behind it) may emit these and nothing else: no free-form expressions, no
generated code, no way to choose or order stops. Selecting and ordering stays
the solver's job — that invariant is the whole point of
``wiki_storage/wiki/concepts/llm-in-the-loop-planning.md``.

Each form enters the MILP through one of three doors:

* **soft, in the objective** — ``BoostCategory`` multiplies a place's score.
  Nothing becomes impossible; the route just drifts toward the taste.
* **hard, before the model exists** — ``ExcludeCategory`` / ``ExcludePlace``
  drop places from the pool, so they never become variables at all.
* **hard, inside the model** — ``RequirePlace`` / ``MinCategory`` /
  ``MaxCategory`` / ``MaxStops`` become one linear constraint each.

The rule of thumb the design page insists on: **taste is soft, requirements
are hard.** Encoding a mild preference as a hard constraint manufactures
empty plans ("I like coffee" should never produce "no plan exists").

Validation lives at the API boundary (Pydantic, ``api.py``): unknown type,
unknown category, unknown id, or an out-of-range factor is a 422 and never
reaches this module. These dataclasses are therefore plain data.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from pho_engine.models import Place


@dataclass(frozen=True)
class BoostCategory:
    """Soft taste: multiply the score of every place in ``category``."""

    category: str
    factor: float


@dataclass(frozen=True)
class ExcludeCategory:
    """Hard filter: no place in ``category`` may be considered."""

    category: str


@dataclass(frozen=True)
class ExcludePlace:
    """Hard filter: this one place may not be considered."""

    id: str


@dataclass(frozen=True)
class RequirePlace:
    """Hard rule: this place must appear in the plan."""

    id: str


@dataclass(frozen=True)
class MinCategory:
    """Hard rule: visit at least ``count`` places of ``category``."""

    category: str
    count: int


@dataclass(frozen=True)
class MaxCategory:
    """Hard rule: visit at most ``count`` places of ``category``."""

    category: str
    count: int


@dataclass(frozen=True)
class MaxStops:
    """Hard rule: the plan may hold at most ``count`` stops."""

    count: int


Constraint = (
    BoostCategory
    | ExcludeCategory
    | ExcludePlace
    | RequirePlace
    | MinCategory
    | MaxCategory
    | MaxStops
)


@dataclass(frozen=True)
class Applied:
    """Everything the rest of the engine needs, derived from a constraint list.

    Attributes:
        pool: the places surviving the hard filters — what the candidate
            pre-filter and then the model may draw from.
        weights: place id → score multiplier (1.0 unless boosted).
        required_ids: places that must be visited. Needed in two places: the
            candidate pre-filter must force them in, and the model pins them
            with ``visit[i] = 1``.
        min_category / max_category: category → count bounds.
        max_stops: overall stop ceiling, or None.
    """

    pool: list[Place]
    weights: dict[str, float]
    required_ids: frozenset[str]
    min_category: dict[str, int]
    max_category: dict[str, int]
    max_stops: int | None


def apply_constraints(places: list[Place], *, constraints: Sequence[Constraint]) -> Applied:
    """Turn a constraint list into a filtered pool, score weights and bounds.

    Pure and idempotent: feeding the result's ``pool`` back in with the same
    constraints yields the same answer, which is what lets the API layer call
    this once for the pool and the solver call it again for the weights.

    Args:
        places: the places to filter and weigh.
        constraints: the validated constraint list (may be empty).

    Returns:
        An :class:`Applied` bundle.

    Notes:
        **Required places always survive the filters.** "No museums, but we
        must see the Phở Museum" is a coherent request (specific beats
        general) — and technically a required place that got filtered out
        would be pinned by ``visit[i] = 1`` while absent from the model,
        which is infeasible by construction.

        Repeated constraints of the same kind merge to the **strictest**
        bound, so the result never depends on their order. Repeated boosts
        multiply.
    """
    excluded_categories = {c.category for c in constraints if isinstance(c, ExcludeCategory)}
    excluded_ids = {c.id for c in constraints if isinstance(c, ExcludePlace)}
    required_ids = frozenset(c.id for c in constraints if isinstance(c, RequirePlace))

    pool = [
        place
        for place in places
        if place.id in required_ids
        or (place.category not in excluded_categories and place.id not in excluded_ids)
    ]

    weights = {place.id: 1.0 for place in pool}
    min_category: dict[str, int] = {}
    max_category: dict[str, int] = {}
    max_stops: int | None = None
    for constraint in constraints:
        if isinstance(constraint, BoostCategory):
            for place in pool:
                if place.category == constraint.category:
                    weights[place.id] *= constraint.factor
        elif isinstance(constraint, MinCategory):
            previous = min_category.get(constraint.category, 0)
            min_category[constraint.category] = max(previous, constraint.count)
        elif isinstance(constraint, MaxCategory):
            previous = max_category.get(constraint.category, constraint.count)
            max_category[constraint.category] = min(previous, constraint.count)
        elif isinstance(constraint, MaxStops):
            max_stops = constraint.count if max_stops is None else min(max_stops, constraint.count)

    return Applied(
        pool=pool,
        weights=weights,
        required_ids=required_ids,
        min_category=min_category,
        max_category=max_category,
        max_stops=max_stops,
    )
