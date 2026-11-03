"""Driving routes from an OSRM server, cached so repeat trips skip the API.

Callers depend on the ``RoutingProvider`` protocol, so the OSRM client can
be replaced (self-hosted OSRM, GraphHopper, a test fake) without changes
elsewhere.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

import requests
from django.conf import settings
from django.core.cache import cache

from .exceptions import RouteNotFound, RoutingProviderError
from .geocoding import Coordinates
from .geometry import simplify_path

logger = logging.getLogger(__name__)

METERS_PER_MILE = 1609.344

# ~50 m: shrinks a cross-country route from ~35k to ~2.6k points (868 KB to
# 59 KB) with no visible change on a map.
DISPLAY_TOLERANCE_DEGREES = 0.0005

# OSRM codes meaning "these points can't be connected by road", as opposed
# to a malformed request or a server problem.
_NO_ROUTE_CODES = frozenset({"NoRoute", "NoSegment"})


@dataclass(frozen=True, slots=True)
class Route:
    distance_miles: float
    duration_seconds: float
    # Points along the road in GeoJSON order: (longitude, latitude).
    path: tuple[tuple[float, float], ...]
    # A lighter copy of ``path`` for drawing; calculations use ``path``.
    display_path: tuple[tuple[float, float], ...] = ()

    def to_geojson(self) -> dict:
        """The route as a GeoJSON LineString, using the display path when available."""
        points = self.display_path or self.path
        return {
            "type": "LineString",
            "coordinates": [[round(lon, 5), round(lat, 5)] for lon, lat in points],
        }


class RoutingProvider(Protocol):
    def route(self, start: Coordinates, finish: Coordinates) -> Route: ...


class OSRMClient:
    """Client for the OSRM ``route`` service (https://project-osrm.org/docs/v5.24.0/api/)."""

    def __init__(
        self, base_url: str, timeout: float, session: requests.Session | None = None
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._session = session or requests.Session()
        self._session.headers["User-Agent"] = "fuel-route-optimizer/1.0"

    def route(self, start: Coordinates, finish: Coordinates) -> Route:
        waypoints = ";".join(f"{c.longitude:.6f},{c.latitude:.6f}" for c in (start, finish))
        url = f"{self._base_url}/route/v1/driving/{waypoints}"
        params = {"overview": "full", "geometries": "geojson", "steps": "false"}

        try:
            response = self._session.get(url, params=params, timeout=self._timeout)
        except requests.RequestException as exc:
            logger.warning("OSRM request failed: %s", exc)
            raise RoutingProviderError("The routing service is unavailable.") from exc

        payload = _json_or_none(response)
        code = payload.get("code") if payload else None
        if code in _NO_ROUTE_CODES:
            raise RouteNotFound("No drivable route was found between these locations.")
        if response.status_code != 200 or code != "Ok" or not payload.get("routes"):
            logger.warning("OSRM returned HTTP %s, code %s", response.status_code, code)
            raise RoutingProviderError("The routing service returned an error.")

        best = payload["routes"][0]
        path = tuple((lon, lat) for lon, lat in best["geometry"]["coordinates"])
        return Route(
            distance_miles=best["distance"] / METERS_PER_MILE,
            duration_seconds=best["duration"],
            path=path,
            # Simplified once here, so cached routes don't pay for it again.
            display_path=tuple(simplify_path(path, DISPLAY_TOLERANCE_DEGREES)),
        )


class CachedRoutingProvider:
    """Caches another provider's routes in the Django cache."""

    def __init__(self, provider: RoutingProvider, namespace: str, timeout: int) -> None:
        self._provider = provider
        self._namespace = namespace
        self._timeout = timeout

    def route(self, start: Coordinates, finish: Coordinates) -> Route:
        key = self._cache_key(start, finish)
        if (cached := cache.get(key)) is not None:
            return cached
        route = self._provider.route(start, finish)
        cache.set(key, route, self._timeout)
        return route

    def _cache_key(self, start: Coordinates, finish: Coordinates) -> str:
        # Four decimals is ~11 m: the same trip typed slightly differently
        # shares an entry, without merging genuinely different places.
        points = ":".join(f"{c.latitude:.4f},{c.longitude:.4f}" for c in (start, finish))
        return f"route:{self._namespace}:{points}"


@lru_cache(maxsize=1)
def get_routing_provider() -> RoutingProvider:
    """Return the process-wide, cached routing provider configured in settings."""
    return CachedRoutingProvider(
        OSRMClient(settings.OSRM_BASE_URL, timeout=settings.ROUTING_TIMEOUT_SECONDS),
        namespace="osrm",
        timeout=settings.ROUTE_CACHE_TIMEOUT,
    )


def _json_or_none(response: requests.Response) -> dict | None:
    try:
        payload = response.json()
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None
