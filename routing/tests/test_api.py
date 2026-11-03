from decimal import Decimal
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from routing.models import FuelStation
from routing.services.exceptions import RouteNotFound, RoutingProviderError
from routing.services.geocoding import get_place_index
from routing.services.route_stations import get_station_index
from routing.services.routing_client import Route


class FakeRouter:
    """Stands in for OSRM: a straight three-point route between the requested points."""

    def __init__(self, distance_miles: float = 780.0, error: Exception | None = None):
        self.distance_miles = distance_miles
        self.error = error
        self.calls = 0

    def route(self, start, finish):
        self.calls += 1
        if self.error:
            raise self.error
        middle = ((start.longitude + finish.longitude) / 2, (start.latitude + finish.latitude) / 2)
        return Route(
            distance_miles=self.distance_miles,
            duration_seconds=11 * 3600,
            path=((start.longitude, start.latitude), middle, (finish.longitude, finish.latitude)),
        )


class TripApiTestCase(TestCase):
    def setUp(self):
        get_station_index.cache_clear()
        self.addCleanup(get_station_index.cache_clear)
        self.router = FakeRouter()
        patcher = mock.patch(
            "routing.services.trip_planner.get_routing_provider", return_value=self.router
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def add_station(self, opis_id: int, city: str, state: str, price: str, lat=None, lon=None):
        place = get_place_index().lookup(city, state)
        FuelStation.objects.create(
            opis_id=opis_id,
            name=f"STOP #{opis_id}",
            address="I-35",
            city=city,
            state=state,
            rack_id=1,
            retail_price=Decimal(price),
            latitude=lat if lat is not None else place.coordinates.latitude,
            longitude=lon if lon is not None else place.coordinates.longitude,
        )

    def add_dallas_to_denver_stations(self):
        dallas = get_place_index().lookup("Dallas", "TX").coordinates
        denver = get_place_index().lookup("Denver", "CO").coordinates
        self.add_station(1, "Dallas", "TX", "3.00")
        # Halfway along the fake straight route.
        self.add_station(
            2,
            "Midway",
            "TX",
            "2.80",
            lat=(dallas.latitude + denver.latitude) / 2,
            lon=(dallas.longitude + denver.longitude) / 2,
        )


class TripPlanViewTests(TripApiTestCase):
    url = reverse("routing:route")

    def post(self, start="Dallas, TX", finish="Denver, CO"):
        return self.client.post(self.url, {"start": start, "finish": finish}, content_type="application/json")

    def test_returns_fuel_plan(self):
        self.add_dallas_to_denver_stations()

        response = self.post()

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["start"]["label"], "Dallas, TX")
        self.assertEqual(body["finish"]["label"], "Denver, CO")
        self.assertEqual(body["distance_miles"], 780.0)
        self.assertEqual(body["total_gallons"], "78.000")
        dallas, midway = body["fuel_stops"]
        self.assertEqual((dallas["opis_id"], midway["opis_id"]), (1, 2))
        # Only enough at Dallas to reach the cheaper midway station.
        self.assertAlmostEqual(float(dallas["gallons"]), midway["mile_marker"] / 10, delta=0.01)
        self.assertEqual(midway["price_per_gallon"], "2.800")
        self.assertEqual(
            Decimal(body["total_fuel_cost"]), Decimal(dallas["cost"]) + Decimal(midway["cost"])
        )
        self.assertEqual(body["route"]["type"], "LineString")
        self.assertIn("/api/route/map/?start=Dallas%2C+TX&finish=Denver%2C+CO", body["map_url"])

    def test_makes_one_routing_call(self):
        self.add_dallas_to_denver_stations()

        self.post()

        self.assertEqual(self.router.calls, 1)

    def test_accepts_coordinates(self):
        self.add_dallas_to_denver_stations()

        response = self.post(start="32.7767,-96.7970")

        self.assertEqual(response.status_code, 200)

    def test_missing_field_is_a_validation_error(self):
        response = self.client.post(self.url, {"start": "Dallas, TX"}, content_type="application/json")

        self.assertEqual(response.status_code, 400)
        error = response.json()["error"]
        self.assertEqual(error["code"], "invalid_request")
        self.assertIn("finish", error["fields"])

    def test_unknown_location_is_400(self):
        response = self.post(start="Atlantis, TX")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "location_not_found")
        self.assertEqual(self.router.calls, 0)

    def test_no_route_is_422(self):
        self.router.error = RouteNotFound("No drivable route.")

        response = self.post(start="Honolulu, HI")

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "route_not_found")

    def test_gap_beyond_vehicle_range_is_422(self):
        self.add_station(1, "Dallas", "TX", "3.00")  # Nothing else for 780 miles.

        response = self.post()

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "fuel_range_exceeded")

    def test_routing_provider_failure_is_503(self):
        self.router.error = RoutingProviderError("The routing service is unavailable.")

        response = self.post()

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"]["code"], "routing_unavailable")

    def test_get_is_not_allowed(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.json()["error"]["code"], "method_not_allowed")


class TripMapViewTests(TripApiTestCase):
    url = reverse("routing:route-map")

    def test_renders_plan_on_a_map(self):
        self.add_dallas_to_denver_stations()

        response = self.client.get(self.url, {"start": "Dallas, TX", "finish": "Denver, CO"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="plan-data"')
        self.assertContains(response, "leaflet@1.9.4")
        # Tile requests must carry a Referer, or OpenStreetMap blocks them.
        self.assertContains(response, 'referrerPolicy: "strict-origin-when-cross-origin"')
        self.assertContains(response, '"total_fuel_cost": ')
        self.assertContains(response, "STOP #2")

    def test_planning_error_is_shown_on_the_page(self):
        response = self.client.get(self.url, {"start": "Atlantis, TX", "finish": "Denver, CO"})

        self.assertContains(response, "Could not find &#x27;Atlantis, TX&#x27;", status_code=400)

    def test_missing_parameters_explain_usage(self):
        response = self.client.get(self.url)

        self.assertContains(response, "?start=", status_code=400)


class IndexViewTests(TestCase):
    def test_lists_endpoints(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("plan_trip", response.json()["endpoints"])
