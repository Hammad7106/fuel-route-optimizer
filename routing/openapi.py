"""OpenAPI documentation for the API, served as Swagger UI at /api/docs/.

Kept here so the views stay focused on behaviour.
"""

from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers

from .serializers import TripPlanSerializer, TripRequestSerializer


def _error(code: str, message: str, **extra) -> dict:
    return {"error": {"code": code, "message": message, **extra}}


ERROR_SCHEMA = {
    "type": "object",
    "properties": {
        "error": {
            "type": "object",
            "properties": {
                "code": {"type": "string"},
                "message": {"type": "string"},
                "fields": {
                    "type": "object",
                    "description": "Per-field messages; only for invalid_request.",
                },
            },
            "required": ["code", "message"],
        }
    },
}


def _error_response(description: str, *examples: tuple[str, dict]) -> OpenApiResponse:
    return OpenApiResponse(
        response=ERROR_SCHEMA,
        description=description,
        examples=[OpenApiExample(name, value=value) for name, value in examples],
    )


plan_trip_schema = extend_schema(
    summary="Plan the cheapest fuel stops for a trip",
    description=(
        "Returns the route, where to refuel and how much to buy, and the total fuel cost. "
        "The vehicle fills up at the start and arrives empty, so the cost covers exactly "
        "the fuel used (miles ÷ 10 MPG)."
    ),
    tags=["Trips"],
    request=TripRequestSerializer,
    responses={
        200: TripPlanSerializer,
        400: _error_response(
            "Invalid request, or a location that can't be found.",
            (
                "Unknown location",
                _error(
                    "location_not_found",
                    "Could not find 'Atlantis, TX'. Use 'City, ST' (e.g. 'Chicago, IL') "
                    "or 'lat,lng' (e.g. '41.88,-87.63').",
                ),
            ),
            (
                "Missing field",
                _error(
                    "invalid_request",
                    "The request is invalid.",
                    fields={"finish": ["This field is required."]},
                ),
            ),
        ),
        422: _error_response(
            "No drivable route, or a stretch with no station within range.",
            ("No route", _error("route_not_found", "No drivable route was found between these locations.")),
            (
                "Out of range",
                _error(
                    "fuel_range_exceeded",
                    "No fuel station between mile 100 and mile 700, "
                    "which is beyond the vehicle's 500-mile range.",
                ),
            ),
        ),
        503: _error_response(
            "The routing service failed or timed out.",
            ("Routing down", _error("routing_unavailable", "The routing service is unavailable.")),
        ),
    },
    examples=[
        OpenApiExample("Dallas → Denver", value={"start": "Dallas, TX", "finish": "Denver, CO"}, request_only=True),
        OpenApiExample(
            "New York → Los Angeles",
            value={"start": "New York, NY", "finish": "Los Angeles, CA"},
            request_only=True,
        ),
        OpenApiExample(
            "Coordinates", value={"start": "41.8781,-87.6298", "finish": "Nashville, TN"}, request_only=True
        ),
        OpenApiExample(
            "Error: unknown location",
            value={"start": "Atlantis, TX", "finish": "Denver, CO"},
            request_only=True,
        ),
    ],
)

health_schema = extend_schema(
    summary="Health check",
    tags=["Service"],
    responses=inline_serializer(
        "Health",
        {
            "status": serializers.CharField(),
            "stations_loaded": serializers.IntegerField(),
            "routing_provider": serializers.CharField(),
        },
    ),
)
