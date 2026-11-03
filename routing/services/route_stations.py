"""Find the fuel stations along a route and where on the trip each one is.

Stations are held in memory once per process. For each route, a KD-tree is
built over the route's points and every station is matched to its nearest
point in a single vectorized query (~20 ms for a cross-country trip).
Points are compared as 3D unit vectors, so straight-line distances are
exact chords of the sphere, without lat/lng distortion.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache

import numpy as np
from scipy.spatial import cKDTree

from ..models import FuelStation
from .geocoding import Coordinates
from .routing_client import Route

EARTH_RADIUS_MILES = 3958.8

# OSRM drops points on straight roads, leaving gaps of several miles. Filling
# them in keeps "nearest route point" within a few hundred feet of the road.
MAX_POINT_SPACING_MILES = 0.5


@dataclass(frozen=True, slots=True)
class Station:
    opis_id: int
    name: str
    address: str
    city: str
    state: str
    price: Decimal
    coordinates: Coordinates


@dataclass(frozen=True, slots=True)
class StationOnRoute:
    station: Station
    # Distance from the start of the trip to the point on the route nearest the station.
    mile_marker: float
    # Straight-line distance from that point to the station.
    off_route_miles: float


class StationIndex:
    def __init__(self, stations: Sequence[Station]) -> None:
        self._stations = tuple(stations)
        self._vectors = _unit_vectors(
            np.array([s.coordinates.latitude for s in self._stations], dtype=float),
            np.array([s.coordinates.longitude for s in self._stations], dtype=float),
        )

    @classmethod
    def from_database(cls) -> StationIndex:
        return cls(
            [
                Station(
                    opis_id=s.opis_id,
                    name=s.name,
                    address=s.address,
                    city=s.city,
                    state=s.state,
                    price=s.retail_price,
                    coordinates=Coordinates(s.latitude, s.longitude),
                )
                for s in FuelStation.objects.all()
            ]
        )

    def __len__(self) -> int:
        return len(self._stations)

    def along(self, route: Route, radius_miles: float) -> list[StationOnRoute]:
        """Return stations within ``radius_miles`` of the route, ordered by mile marker."""
        if not self._stations or not route.path:
            return []

        lon, lat = np.radians(np.asarray(route.path, dtype=float)).T
        lat, lon = _densify(lat, lon, MAX_POINT_SPACING_MILES / EARTH_RADIUS_MILES)
        mile_markers = _cumulative_miles(lat, lon)
        # Scale to the provider's distance so the last marker equals the trip length.
        if mile_markers[-1] > 0:
            mile_markers *= route.distance_miles / mile_markers[-1]

        tree = cKDTree(_unit_vectors(lat, lon, radians=True))
        max_chord = 2 * np.sin(radius_miles / (2 * EARTH_RADIUS_MILES))
        chords, nearest = tree.query(self._vectors, distance_upper_bound=max_chord)

        hits = np.flatnonzero(np.isfinite(chords))
        off_route = 2 * EARTH_RADIUS_MILES * np.arcsin(chords[hits] / 2)
        found = [
            StationOnRoute(self._stations[i], float(mile_markers[nearest[i]]), float(off))
            for i, off in zip(hits, off_route, strict=True)
        ]
        found.sort(key=lambda s: (s.mile_marker, s.station.price))
        return found


@lru_cache(maxsize=1)
def get_station_index() -> StationIndex:
    """Return the process-wide station index, loaded from the database on first use.

    Stations are loaded before the server starts (see ``load_stations``), so
    the index is built once per worker and never goes stale while it runs.
    """
    return StationIndex.from_database()


def _unit_vectors(lat: np.ndarray, lon: np.ndarray, *, radians: bool = False) -> np.ndarray:
    if not radians:
        lat, lon = np.radians(lat), np.radians(lon)
    cos_lat = np.cos(lat)
    return np.column_stack((cos_lat * np.cos(lon), cos_lat * np.sin(lon), np.sin(lat)))


def _angular_steps(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    """Haversine angle (radians) between consecutive points."""
    dlat, dlon = np.diff(lat), np.diff(lon)
    a = np.sin(dlat / 2) ** 2 + np.cos(lat[:-1]) * np.cos(lat[1:]) * np.sin(dlon / 2) ** 2
    return 2 * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def _cumulative_miles(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    return np.concatenate(([0.0], np.cumsum(_angular_steps(lat, lon) * EARTH_RADIUS_MILES)))


def _densify(
    lat: np.ndarray, lon: np.ndarray, max_angle: float
) -> tuple[np.ndarray, np.ndarray]:
    """Insert evenly spaced points so no step is longer than ``max_angle``."""
    if len(lat) < 2:
        return lat, lon
    pieces = np.maximum(1, np.ceil(_angular_steps(lat, lon) / max_angle)).astype(int)
    if (pieces == 1).all():
        return lat, lon

    # For segment i split into n pieces, emit fractions 0, 1/n, ..., (n-1)/n
    # from its start point, then append the route's final point.
    segment = np.repeat(np.arange(len(pieces)), pieces)
    offsets = np.arange(len(segment)) - np.repeat(np.cumsum(pieces) - pieces, pieces)
    fraction = offsets / pieces[segment]
    new_lat = lat[segment] + fraction * (lat[segment + 1] - lat[segment])
    new_lon = lon[segment] + fraction * (lon[segment + 1] - lon[segment])
    return np.append(new_lat, lat[-1]), np.append(new_lon, lon[-1])
