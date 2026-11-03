"""Plan a trip end to end: locations, route, stations along it, fuel stops.

This is the single entry point for the API. Per new trip it makes one
external call (the route); everything else runs on in-memory data.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.conf import settings
from django.db import DatabaseError

from .fuel_planner import FuelPlan, plan_fuel_stops
from .geocoding import get_place_index
from .locations import Location, resolve_location
from .route_stations import get_station_index
from .routing_client import Route, get_routing_provider

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TripPlan:
    start: Location
    finish: Location
    route: Route
    fuel: FuelPlan


def plan_trip(start: str, finish: str) -> TripPlan:
    """Raises a ``RoutePlanningError`` subclass when the trip can't be planned."""
    places = get_place_index()
    start_location = resolve_location(start, places)
    finish_location = resolve_location(finish, places)

    route = get_routing_provider().route(start_location.coordinates, finish_location.coordinates)
    stations = get_station_index().along(route, settings.STATION_SEARCH_RADIUS_MILES)
    fuel = plan_fuel_stops(
        stations,
        route.distance_miles,
        max_range_miles=settings.VEHICLE_MAX_RANGE_MILES,
        mpg=settings.VEHICLE_MPG,
        merge_within_miles=settings.FUEL_STOP_MERGE_MILES,
    )
    return TripPlan(start=start_location, finish=finish_location, route=route, fuel=fuel)


def warm_up() -> None:
    """Load the place and station indexes now rather than on the first request.

    If stations aren't loaded yet (e.g. before ``migrate``/``load_stations``
    in development), nothing is cached and loading is retried on first use.
    """
    get_place_index()
    try:
        stations = get_station_index()
    except DatabaseError:
        stations = None
    if not stations:
        get_station_index.cache_clear()
        logger.warning("No fuel stations loaded; run `manage.py load_stations`.")
