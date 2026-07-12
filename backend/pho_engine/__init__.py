"""Phở around — OR/LP itinerary engine (phase 2).

The single public entry point is :func:`plan_itinerary`: give it candidate
places, a start location and the time/money budgets, get back an optimized
``Itinerary``. Everything else in the package is an implementation detail.
"""

from pho_engine.models import Itinerary, Place, Start, Stop
from pho_engine.seed import load_seed_places
from pho_engine.solver import plan_itinerary

__all__ = [
    "Itinerary",
    "Place",
    "Start",
    "Stop",
    "load_seed_places",
    "plan_itinerary",
]
