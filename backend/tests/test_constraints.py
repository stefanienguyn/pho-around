"""Tests for the constraint vocabulary and how it resolves into an Applied bundle.

Pure Python — no solver, no network, no LLM. This is where the correctness of
the constraint layer lives; the model boundary is tested separately.
"""

from pho_engine.constraints import (
    Applied,
    BoostCategory,
    ExcludeCategory,
    ExcludePlace,
    FirstCategory,
    FirstPlace,
    MaxCategory,
    MaxStops,
    MinCategory,
    RequirePlace,
    apply_constraints,
)
from pho_engine.models import Place


def make_place(id: str, *, category: str = "food", score: float = 4.0) -> Place:
    """A bare place; only id/category/score matter to the constraint layer."""
    return Place(
        id=id,
        name=id,
        category=category,
        district="test",
        price_per_person_vnd=0,
        avg_minutes=30,
        score=score,
        lat=10.78,
        lng=106.70,
    )


PLACES = [
    make_place("pho", category="food"),
    make_place("banh-mi", category="food"),
    make_place("cafe-a", category="coffee"),
    make_place("cafe-b", category="coffee"),
    make_place("mall", category="shopping"),
]


def test_no_constraints_changes_nothing() -> None:
    """An empty list is the identity: same pool, neutral weights, no bounds."""
    applied = apply_constraints(PLACES, constraints=[])
    assert applied.pool == PLACES
    assert set(applied.weights.values()) == {1.0}
    assert applied.required_ids == frozenset()
    assert applied.min_category == {} and applied.max_category == {}
    assert applied.max_stops is None


def test_exclusions_drop_places_from_the_pool() -> None:
    """Category and single-place exclusions both filter before the model exists."""
    applied = apply_constraints(
        PLACES, constraints=[ExcludeCategory(category="shopping"), ExcludePlace(id="cafe-a")]
    )
    assert [p.id for p in applied.pool] == ["pho", "banh-mi", "cafe-b"]
    # Excluded places carry no weight entry either — they simply don't exist here.
    assert "mall" not in applied.weights


def test_required_place_survives_its_category_being_excluded() -> None:
    """ "No shopping, but we're definitely going to that mall" is coherent.

    Also a correctness requirement: a required place filtered out of the pool
    would be pinned by visit[i]=1 while absent from the model — infeasible by
    construction.
    """
    applied = apply_constraints(
        PLACES, constraints=[ExcludeCategory(category="shopping"), RequirePlace(id="mall")]
    )
    assert any(p.id == "mall" for p in applied.pool)
    assert applied.required_ids == frozenset({"mall"})


def test_boost_multiplies_only_its_category() -> None:
    """A boost touches its category's weights and leaves the rest neutral."""
    applied = apply_constraints(PLACES, constraints=[BoostCategory(category="coffee", factor=1.25)])
    assert applied.weights["cafe-a"] == 1.25
    assert applied.weights["cafe-b"] == 1.25
    assert applied.weights["pho"] == 1.0


def test_repeated_bounds_merge_to_the_strictest_regardless_of_order() -> None:
    """Two caps on the same thing → the tighter one wins, either way round."""
    forwards = apply_constraints(
        PLACES,
        constraints=[
            MaxCategory(category="coffee", count=2),
            MaxCategory(category="coffee", count=1),
            MinCategory(category="food", count=1),
            MinCategory(category="food", count=2),
            MaxStops(count=5),
            MaxStops(count=3),
        ],
    )
    backwards = apply_constraints(
        PLACES,
        constraints=[
            MaxStops(count=3),
            MaxStops(count=5),
            MinCategory(category="food", count=2),
            MinCategory(category="food", count=1),
            MaxCategory(category="coffee", count=1),
            MaxCategory(category="coffee", count=2),
        ],
    )
    for applied in (forwards, backwards):
        assert applied.max_category == {"coffee": 1}
        assert applied.min_category == {"food": 2}
        assert applied.max_stops == 3


def test_applying_twice_is_the_same_as_applying_once() -> None:
    """Idempotence: the API filters the pool, then the solver re-derives weights.

    Both call sites run this function, so a second pass over an already
    filtered pool must not change anything.
    """
    constraints = [
        ExcludeCategory(category="shopping"),
        BoostCategory(category="coffee", factor=1.25),
        MaxStops(count=3),
    ]
    once = apply_constraints(PLACES, constraints=constraints)
    twice = apply_constraints(once.pool, constraints=constraints)
    assert isinstance(twice, Applied)
    assert [p.id for p in twice.pool] == [p.id for p in once.pool]
    assert twice.weights == once.weights
    assert twice.max_stops == once.max_stops


def test_first_place_is_also_required_and_survives_filters() -> None:
    """ "Start with phở" implies visiting phở — even if food is excluded."""
    applied = apply_constraints(
        PLACES, constraints=[FirstPlace(id="pho"), ExcludeCategory(category="food")]
    )
    assert applied.first_ids == {"pho"}
    assert "pho" in applied.required_ids
    assert [p.id for p in applied.pool if p.category == "food"] == ["pho"]


def test_first_category_is_recorded_without_touching_the_pool() -> None:
    """An anchor on a category filters nothing; the solver decides which member."""
    applied = apply_constraints(PLACES, constraints=[FirstCategory(category="coffee")])
    assert applied.first_categories == {"coffee"}
    assert applied.required_ids == frozenset()
    assert len(applied.pool) == len(PLACES)
