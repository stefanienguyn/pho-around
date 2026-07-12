"""Tests for the core data types."""

from pho_engine.models import Itinerary, Place, Start, Stop


def test_place_round_trips_fields() -> None:
    """A Place holds its schema fields with the expected types/values."""
    p = Place(
        id="test-spot",
        name="Test Spot",
        category="coffee",
        district="District 1",
        price_per_person_vnd=55000,
        avg_minutes=60,
        score=4.2,
        lat=10.78,
        lng=106.70,
        tags=("coffee", "work"),
    )
    assert p.id == "test-spot"
    assert p.price_per_person_vnd == 55000
    assert p.avg_minutes == 60
    assert p.score == 4.2
    assert p.tags == ("coffee", "work")


def test_start_defaults() -> None:
    """The depot needs only coordinates; it carries no cost or dwell."""
    s = Start(lat=10.77, lng=106.70)
    assert s.name == "Start"
    assert (s.lat, s.lng) == (10.77, 106.70)


def test_itinerary_place_ids_are_in_route_order() -> None:
    """place_ids reflects stop order, so tests can assert routes cheaply."""
    a = Place("a", "A", "food", "District 1", 0, 10, 4.0, 10.0, 106.0)
    b = Place("b", "B", "food", "District 1", 0, 10, 4.0, 10.1, 106.1)
    itin = Itinerary(
        stops=(
            Stop(order=1, place=a, travel_minutes_from_prev=5.0),
            Stop(order=2, place=b, travel_minutes_from_prev=7.0),
        ),
        total_score=8.0,
        total_minutes=32.0,
        total_cost_vnd=0,
    )
    assert itin.place_ids == ["a", "b"]
