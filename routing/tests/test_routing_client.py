from unittest import mock

import requests
from django.core.cache import cache
from django.test import SimpleTestCase

from routing.services.exceptions import RouteNotFound, RoutingProviderError
from routing.services.geocoding import Coordinates
from routing.services.routing_client import CachedRoutingProvider, OSRMClient, Route

NEW_YORK = Coordinates(40.7128, -74.0060)
CHICAGO = Coordinates(41.8781, -87.6298)

OSRM_OK = {
    "code": "Ok",
    "routes": [
        {
            "distance": 1_272_201.0,
            "duration": 53_440.8,
            "geometry": {
                "type": "LineString",
                "coordinates": [[-74.006, 40.7128], [-87.6298, 41.8781]],
            },
        }
    ],
}


def osrm_response(status: int, payload: dict | None = None, text: str = "") -> mock.Mock:
    response = mock.Mock(status_code=status)
    response.json.side_effect = (lambda: payload) if payload is not None else ValueError(text)
    return response


class OSRMClientTests(SimpleTestCase):
    def setUp(self):
        self.session = mock.Mock(headers={})
        self.client = OSRMClient("https://osrm.test/", timeout=5, session=self.session)

    def test_parses_route(self):
        self.session.get.return_value = osrm_response(200, OSRM_OK)

        route = self.client.route(NEW_YORK, CHICAGO)

        self.assertAlmostEqual(route.distance_miles, 790.5, places=1)
        self.assertEqual(route.duration_seconds, 53_440.8)
        self.assertEqual(route.path, ((-74.006, 40.7128), (-87.6298, 41.8781)))

    def test_requests_full_geometry_with_lng_lat_order_and_timeout(self):
        self.session.get.return_value = osrm_response(200, OSRM_OK)

        self.client.route(NEW_YORK, CHICAGO)

        url = self.session.get.call_args.args[0]
        kwargs = self.session.get.call_args.kwargs
        self.assertEqual(
            url, "https://osrm.test/route/v1/driving/-74.006000,40.712800;-87.629800,41.878100"
        )
        self.assertEqual(kwargs["params"]["overview"], "full")
        self.assertEqual(kwargs["params"]["geometries"], "geojson")
        self.assertEqual(kwargs["timeout"], 5)

    def test_no_route_is_route_not_found(self):
        self.session.get.return_value = osrm_response(
            400, {"code": "NoRoute", "message": "Impossible route between points"}
        )

        with self.assertRaises(RouteNotFound):
            self.client.route(NEW_YORK, CHICAGO)

    def test_provider_failures_are_provider_errors(self):
        cases = {
            "timeout": requests.Timeout("slow"),
            "connection error": requests.ConnectionError("down"),
            "rate limited": osrm_response(429, text="Too Many Requests"),
            "server error": osrm_response(502, text="<html>Bad Gateway</html>"),
            "invalid request": osrm_response(400, {"code": "InvalidValue"}),
            "no routes": osrm_response(200, {"code": "Ok", "routes": []}),
        }
        for name, outcome in cases.items():
            with self.subTest(name):
                self.session.get.side_effect = outcome if isinstance(outcome, Exception) else None
                self.session.get.return_value = outcome
                with (
                    self.assertLogs("routing.services.routing_client", "WARNING"),
                    self.assertRaises(RoutingProviderError),
                ):
                    self.client.route(NEW_YORK, CHICAGO)


class CachedRoutingProviderTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.provider = mock.Mock()
        self.provider.route.return_value = Route(790.5, 53_440.8, ((-74.0, 40.7),))
        self.cached = CachedRoutingProvider(self.provider, namespace="test", timeout=60)

    def test_repeat_trip_calls_provider_once(self):
        first = self.cached.route(NEW_YORK, CHICAGO)
        second = self.cached.route(NEW_YORK, CHICAGO)

        self.assertEqual(first, second)
        self.provider.route.assert_called_once()

    def test_nearby_inputs_share_an_entry(self):
        self.cached.route(NEW_YORK, CHICAGO)
        self.cached.route(Coordinates(40.71281, -74.00601), CHICAGO)

        self.provider.route.assert_called_once()

    def test_different_trips_are_cached_separately(self):
        self.cached.route(NEW_YORK, CHICAGO)
        self.cached.route(CHICAGO, NEW_YORK)

        self.assertEqual(self.provider.route.call_count, 2)

    def test_errors_are_not_cached(self):
        route = self.provider.route.return_value
        self.provider.route.side_effect = [RoutingProviderError("down"), route]

        with self.assertRaises(RoutingProviderError):
            self.cached.route(NEW_YORK, CHICAGO)
        self.cached.route(NEW_YORK, CHICAGO)

        self.assertEqual(self.provider.route.call_count, 2)
