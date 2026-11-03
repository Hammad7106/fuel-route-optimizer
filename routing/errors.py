"""Turn errors into one consistent API error format:

    {"error": {"code": "location_not_found", "message": "...", "fields": {...}}}

``fields`` is present only for request validation errors.
"""

from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from .services.exceptions import (
    FuelRangeExceeded,
    LocationNotFound,
    RouteNotFound,
    RoutePlanningError,
    RoutingProviderError,
)

PLANNING_ERRORS: dict[type[RoutePlanningError], tuple[int, str]] = {
    LocationNotFound: (status.HTTP_400_BAD_REQUEST, "location_not_found"),
    RouteNotFound: (status.HTTP_422_UNPROCESSABLE_ENTITY, "route_not_found"),
    FuelRangeExceeded: (status.HTTP_422_UNPROCESSABLE_ENTITY, "fuel_range_exceeded"),
    RoutingProviderError: (status.HTTP_503_SERVICE_UNAVAILABLE, "routing_unavailable"),
}


def describe_planning_error(exc: RoutePlanningError) -> tuple[int, dict]:
    http_status, code = PLANNING_ERRORS.get(
        type(exc), (status.HTTP_500_INTERNAL_SERVER_ERROR, "planning_failed")
    )
    return http_status, {"error": {"code": code, "message": str(exc)}}


def api_exception_handler(exc, context) -> Response | None:
    """DRF ``EXCEPTION_HANDLER``."""
    if isinstance(exc, RoutePlanningError):
        http_status, body = describe_planning_error(exc)
        return Response(body, status=http_status)

    response = drf_exception_handler(exc, context)
    if response is None:
        return None  # Unexpected error: let Django return a 500.
    if isinstance(exc, ValidationError):
        error = {"code": "invalid_request", "message": "The request is invalid.", "fields": response.data}
    else:
        error = {"code": exc.default_code, "message": str(response.data.get("detail", exc))}
    response.data = {"error": error}
    return response
