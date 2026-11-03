from decimal import Decimal

from django.test import SimpleTestCase, TestCase

from routing.models import FuelStation
from routing.services.geocoding import Coordinates
from routing.services.route_stations import Station, StationIndex
from routing.services.routing_client import Route

# Along the equator one degree is 69.09 miles in both directions, which
# keeps expected distances easy to reason about.
MILES_PER_DEGREE = 69.09


def station(opis_id: int, lat: float, lon: float, price: str = "3.50") -> Station:
    return Station(opis_id, f"Stop {opis_id}", "", "", "", Decimal(price), Coordinates(lat, lon))


def equator_route(*longitudes: float, distance_miles: float | None = None) -> Route:
    span = (longitudes[-1] - longitudes[0]) * MILES_PER_DEGREE
    return Route(
        distance_miles=span if distance_miles is None else distance_miles,
        duration_seconds=0,
        path=tuple((lon, 0.0) for lon in longitudes),
    )


class StationIndexAlongTests(SimpleTestCase):
    def test_keeps_stations_within_radius_only(self):
        index = StationIndex([station(1, 0.05, 0.5), station(2, 0.3, 0.5)])

        found = index.along(equator_route(0, 0.5, 1), radius_miles=10)

        self.assertEqual([s.station.opis_id for s in found], [1])

    def test_reports_mile_marker_and_off_route_distance(self):
        index = StationIndex([station(1, 0.05, 0.5)])

        (found,) = index.along(equator_route(0, 1), radius_miles=10)

        self.assertAlmostEqual(found.mile_marker, 0.5 * MILES_PER_DEGREE, delta=0.5)
        self.assertAlmostEqual(found.off_route_miles, 0.05 * MILES_PER_DEGREE, delta=0.1)

    def test_long_gaps_between_route_points_are_filled_in(self):
        # Only two points, 69 miles apart: without densifying, the station's
        # nearest point would be an endpoint ~35 miles away.
        index = StationIndex([station(1, 0.02, 0.5)])

        (found,) = index.along(equator_route(0, 1), radius_miles=5)

        self.assertLess(found.off_route_miles, 1.5)

    def test_orders_by_mile_marker(self):
        index = StationIndex([station(1, 0, 0.9), station(2, 0, 0.1), station(3, 0, 0.5)])

        found = index.along(equator_route(0, 1), radius_miles=10)

        self.assertEqual([s.station.opis_id for s in found], [2, 3, 1])

    def test_mile_markers_are_scaled_to_route_distance(self):
        # Roads wind more than the straight line between points.
        index = StationIndex([station(1, 0, 1)])

        (found,) = index.along(equator_route(0, 1, distance_miles=100), radius_miles=10)

        self.assertAlmostEqual(found.mile_marker, 100, delta=0.01)

    def test_empty_inputs(self):
        self.assertEqual(StationIndex([]).along(equator_route(0, 1), radius_miles=10), [])
        empty_route = Route(0, 0, ())
        self.assertEqual(StationIndex([station(1, 0, 0)]).along(empty_route, 10), [])


class StationIndexFromDatabaseTests(TestCase):
    def test_loads_stations(self):
        FuelStation.objects.create(
            opis_id=7,
            name="WOODSHED OF BIG CABIN",
            address="I-44",
            city="Big Cabin",
            state="OK",
            rack_id=307,
            retail_price=Decimal("3.00733333"),
            latitude=36.5376,
            longitude=-95.2208,
        )

        index = StationIndex.from_database()

        self.assertEqual(len(index), 1)
        (found,) = index.along(
            Route(10, 0, ((-95.3, 36.5376), (-95.1, 36.5376))), radius_miles=10
        )
        self.assertEqual(found.station.price, Decimal("3.00733333"))
        self.assertEqual(found.station.coordinates, Coordinates(36.5376, -95.2208))
