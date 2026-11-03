from django.conf import settings
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    """Liveness check that also reports whether the routing API key is configured."""

    def get(self, request: Request) -> Response:
        return Response(
            {
                "status": "ok",
                "routing_api_configured": bool(settings.ORS_API_KEY),
            }
        )
