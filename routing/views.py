from urllib.parse import urlsplit

from django.conf import settings
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import FuelStation


class HealthView(APIView):
    """Liveness check that also reports whether station data is loaded."""

    def get(self, request: Request) -> Response:
        return Response(
            {
                "status": "ok",
                "stations_loaded": FuelStation.objects.count(),
                "routing_provider": urlsplit(settings.OSRM_BASE_URL).hostname,
            }
        )
