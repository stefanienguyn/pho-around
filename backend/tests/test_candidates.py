"""Tests for the candidate pre-filter (the solver's guest list)."""

from pho_engine.candidates import select_candidates
from pho_engine.models import Place, Start
from pho_engine.seed import load_seed_places

START_D1 = Start(lat=10.7797, lng=106.6990)


def make_place(id: str, *, lat: float, lng: float, score: float = 4.0) -> Place:
    """Bare place for filter tests; only position and score matter here."""
    return Place(
        id=id,
        name=id,
        category="food",
        district="test",
        price_per_person_vnd=0,
        avg_minutes=30,
        score=score,
        lat=lat,
        lng=lng,
    )


def test_small_datasets_pass_through_unfiltered() -> None:
    """At or under the cap, everyone is a candidate — no filtering surprises."""
    places = [make_place(f"p{i}", lat=10.7 + i * 0.001, lng=106.7) for i in range(10)]
    assert select_candidates(places, START_D1) == places


def test_full_seed_is_capped_at_forty() -> None:
    """100 seed places → at most k_near + k_best candidates."""
    candidates = select_candidates(load_seed_places(), START_D1)
    assert len(candidates) == 40


def test_far_high_scorer_gets_a_guaranteed_seat() -> None:
    """A distant 5.0 place must survive the filter (the champong rule).

    50 mediocre places crowd the start; one gem sits ~8 km away. Nearest-only
    filtering would drop it; the k_best door must let it in.
    """
    crowd = [make_place(f"near{i}", lat=10.78 + i * 0.0005, lng=106.699) for i in range(50)]
    gem = make_place("far-gem", lat=10.74, lng=106.72, score=5.0)
    candidates = select_candidates(crowd + [gem], START_D1)
    assert any(p.id == "far-gem" for p in candidates)


def test_filter_is_start_relative() -> None:
    """Starting in Quận 7 makes Quận 7 the backbone, not the city centre."""
    d7_start = Start(lat=10.7330, lng=106.7220)
    d7_spots = [make_place(f"d7-{i}", lat=10.733 + i * 0.001, lng=106.722) for i in range(5)]
    centre = [make_place(f"c{i}", lat=10.78 + i * 0.0004, lng=106.699) for i in range(50)]
    candidates = select_candidates(centre + d7_spots, d7_start)
    assert all(any(p.id == f"d7-{i}" for p in candidates) for i in range(5))


def test_must_include_forces_a_place_through_both_doors() -> None:
    """A required place survives even when it is neither near nor high-scoring.

    Without this the pre-filter would drop it and the solver would then pin
    visit[i]=1 on a place that never became a variable — infeasible by
    construction, i.e. a silently empty plan for "we're definitely going here".
    """
    crowd = [make_place(f"near{i}", lat=10.78 + i * 0.0005, lng=106.699) for i in range(60)]
    forgettable = make_place("far-and-dull", lat=10.70, lng=106.78, score=1.0)
    places = crowd + [forgettable]

    assert not any(p.id == "far-and-dull" for p in select_candidates(places, START_D1))
    forced = select_candidates(places, START_D1, must_include=["far-and-dull"])
    assert any(p.id == "far-and-dull" for p in forced)
