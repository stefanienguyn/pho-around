"""Tests for the seed dataset loader."""

from pho_engine.models import CATEGORIES
from pho_engine.seed import load_seed_places


def test_loads_all_seed_places() -> None:
    """The seed file holds the documented 100 places with unique ids.

    The count is asserted exactly on purpose: changing the dataset should be
    a deliberate act that touches this number (30 hand-seeded + 7 discovered
    museums/landmarks + 63 imported from the human's food CSV, 2026-08-18).
    """
    places = load_seed_places()
    assert len(places) == 100
    assert len({p.id for p in places}) == 100


def test_every_category_is_present_and_valid() -> None:
    """All six categories appear, and none is outside the allowed set."""
    categories = {p.category for p in load_seed_places()}
    assert categories == set(CATEGORIES)


def test_coordinates_and_scores_are_populated() -> None:
    """Every row has usable coordinates and an in-range score (A1)."""
    for p in load_seed_places():
        assert p.lat is not None and p.lng is not None
        # Sài Gòn sits around 10.7°N, 106.7°E — cheap sanity box on coords.
        assert 10.6 < p.lat < 11.0, p.id
        assert 106.5 < p.lng < 106.8, p.id
        assert 0.0 <= p.score <= 5.0, p.id
