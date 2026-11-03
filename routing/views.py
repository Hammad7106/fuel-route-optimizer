from urllib.parse import urlsplit

from django.conf import settings
from django.shortcuts import render
from django.urls import reverse
from django.views import View
from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .errors import describe_planning_error
from .models import FuelStation
from .openapi import health_schema, plan_trip_schema
from .serializers import TripPlanSerializer, TripRequestSerializer
from .services.exceptions import RoutePlanningError
from .services.trip_planner import plan_trip


class IndexView(APIView):
    @extend_schema(exclude=True)
    def get(self, request: Request) -> Response:
        return Response(
            {
                "name": "Fuel Route Optimizer",
                "endpoints": {
                    "plan_trip": f"POST {request.build_absolute_uri(reverse('routing:route'))}",
                    "map": f"GET {request.build_absolute_uri(reverse('routing:route-map'))}"
                    "?start=Dallas, TX&finish=Denver, CO",
                    "health": f"GET {request.build_absolute_uri(reverse('routing:health'))}",
                    "docs": f"GET {request.build_absolute_uri(reverse('swagger-ui'))}",
                },
                "example_request": {"start": "Dallas, TX", "finish": "Denver, CO"},
            }
        )


class HealthView(APIView):
    """Liveness check that also reports whether station data is loaded."""

    @health_schema
    def get(self, request: Request) -> Response:
        return Response(
            {
                "status": "ok",
                "stations_loaded": FuelStation.objects.count(),
                "routing_provider": urlsplit(settings.OSRM_BASE_URL).hostname,
            }
        )


class TripPlanView(APIView):
    """Plan the cheapest fuel stops for a drive between two US locations."""

    @plan_trip_schema
    def post(self, request: Request) -> Response:
        trip_request = TripRequestSerializer(data=request.data)
        trip_request.is_valid(raise_exception=True)
        # Planning errors become error responses in errors.api_exception_handler.
        trip = plan_trip(**trip_request.validated_data)
        return Response(TripPlanSerializer(trip, context={"request": request}).data)


class TripMapView(View):
    """The same plan drawn on a map, for browsers."""

    def get(self, request):
        trip_request = TripRequestSerializer(data=request.GET)
        if not trip_request.is_valid():
            return self._error(request, "Add ?start=City, ST&finish=City, ST to the URL.", 400)
        try:
            trip = plan_trip(**trip_request.validated_data)
        except RoutePlanningError as exc:
            http_status, body = describe_planning_error(exc)
            return self._error(request, body["error"]["message"], http_status)
        plan = TripPlanSerializer(trip, context={"request": request}).data
        return render(request, "routing/map.html", {"plan": plan})

    def _error(self, request, message: str, http_status: int):
        return render(request, "routing/map.html", {"error": message}, status=http_status)
