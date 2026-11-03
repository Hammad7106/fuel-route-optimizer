"""Errors raised by the route planning services.

They describe what went wrong in domain terms; the API layer decides how
each maps to an HTTP response.
"""


class RoutePlanningError(Exception):
    """Base class for errors that end a route planning request."""


class LocationNotFound(RoutePlanningError):
    """A start or finish location could not be resolved to US coordinates."""


class RouteNotFound(RoutePlanningError):
    """The routing provider found no drivable route between the locations."""


class RoutingProviderError(RoutePlanningError):
    """The routing provider failed, timed out or returned an unusable response."""


class FuelRangeExceeded(RoutePlanningError):
    """Part of the route has no fuel station within the vehicle's range."""
