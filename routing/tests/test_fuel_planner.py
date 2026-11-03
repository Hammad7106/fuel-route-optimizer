import random
from decimal import Decimal

import numpy as np
from django.test import SimpleTestCase
from scipy.optimize import linprog

from routing.services.exceptions import FuelRangeExceeded
from routing.services.fuel_planner import plan_fuel_stops
from routing.services.geocoding import Coordinates
from routing.services.route_stations import Station, StationOnRoute

RANGE = 500.0
MPG = 10.0


def at(mile: float, price: str, opis_id: int | None = None) -> StationOnRoute:
    station = Station(
        opis_id=opis_id if opis_id is not None else int(mile * 10),
        name=f"Stop at {mile}",
        address="",
        city="",
        state="",
        price=Decimal(price),
        coordinates=Coordinates(0, 0),
    )
    return StationOnRoute(station, mile_marker=mile, off_route_miles=0.0)


def plan(stations, total_miles):
    return plan_fuel_stops(stations, total_miles, max_range_miles=RANGE, mpg=MPG)


def summary(fuel_plan):
    return [(s.mile_marker, s.gallons) for s in fuel_plan.stops]


class PlanFuelStopsTests(SimpleTestCase):
    def test_short_trip_buys_just_enough_at_the_start(self):
        result = plan([at(0, "3.00")], 300)

        self.assertEqual(summary(result), [(0, Decimal("30.000"))])
        self.assertEqual(result.total_cost, Decimal("90.00"))

    def test_buys_only_enough_to_reach_a_cheaper_station(self):
        result = plan([at(0, "4.00"), at(100, "3.00")], 400)

        self.assertEqual(summary(result), [(0, Decimal("10.000")), (100, Decimal("30.000"))])
        self.assertEqual(result.total_cost, Decimal("130.00"))

    def test_fills_up_when_nothing_cheaper_is_in_range(self):
        result = plan([at(0, "3.00"), at(450, "4.00")], 800)

        self.assertEqual(summary(result), [(0, Decimal("50.000")), (450, Decimal("30.000"))])

    def test_skips_expensive_stations_it_does_not_need(self):
        result = plan([at(0, "3.00"), at(200, "5.00"), at(400, "3.50")], 700)

        self.assertEqual([s.mile_marker for s in result.stops], [0, 400])

    def test_total_gallons_cover_the_whole_trip(self):
        stations = [at(0, "3.40"), at(180, "3.10"), at(420, "3.90"), at(610, "2.95")]

        result = plan(stations, 1000)

        self.assertEqual(result.total_gallons, Decimal("100.000"))

    def test_prefers_fewer_stops_when_prices_tie(self):
        result = plan([at(0, "3.00"), at(100, "3.00"), at(200, "3.00")], 450)

        self.assertEqual(len(result.stops), 1)

    def test_picks_cheapest_of_several_stations_at_the_same_place(self):
        stations = [at(0, "3.50", opis_id=1), at(0, "3.20", opis_id=2), at(0, "3.90", opis_id=3)]

        result = plan(stations, 100)

        self.assertEqual([s.station.opis_id for s in result.stops], [2])

    def test_first_station_past_the_start_charges_fuel_to_reach_it(self):
        result = plan([at(30, "3.00")], 330)

        self.assertEqual(result.starting_gallons, Decimal("3.000"))
        self.assertEqual(result.starting_cost, Decimal("9.00"))
        self.assertEqual(result.total_gallons, Decimal("33.000"))
        self.assertEqual(result.total_cost, Decimal("99.00"))

    def test_stations_at_the_finish_are_ignored(self):
        result = plan([at(0, "3.00"), at(300, "1.00")], 300)

        self.assertEqual([s.mile_marker for s in result.stops], [0])

    def test_accepts_stations_in_any_order(self):
        stations = [at(400, "3.50"), at(0, "3.00"), at(200, "5.00")]

        self.assertEqual([s.mile_marker for s in plan(stations, 700).stops], [0, 400])

    def test_zero_length_trip_needs_no_fuel(self):
        result = plan([at(0, "3.00")], 0)

        self.assertEqual(result.stops, ())
        self.assertEqual(result.total_cost, Decimal("0"))

    def test_gap_beyond_range_is_an_error(self):
        with self.assertRaisesMessage(FuelRangeExceeded, "between mile 100 and mile 700"):
            plan([at(0, "3.00"), at(100, "3.00"), at(700, "3.00")], 900)

    def test_finish_beyond_range_of_last_station_is_an_error(self):
        with self.assertRaises(FuelRangeExceeded):
            plan([at(0, "3.00")], 600)

    def test_first_station_beyond_range_is_an_error(self):
        with self.assertRaises(FuelRangeExceeded):
            plan([at(520, "3.00")], 700)

    def test_no_stations_is_an_error(self):
        with self.assertRaisesMessage(FuelRangeExceeded, "no fuel stations"):
            plan([], 100)


class MergeNearbyStationsTests(SimpleTestCase):
    def merged_plan(self, stations, total_miles, merge_within_miles=25):
        return plan_fuel_stops(
            stations,
            total_miles,
            max_range_miles=RANGE,
            mpg=MPG,
            merge_within_miles=merge_within_miles,
        )

    def test_avoids_tiny_stop_just_before_a_slightly_cheaper_station(self):
        stations = [at(0, "3.30"), at(200, "3.24"), at(201, "3.10")]

        self.assertEqual(len(plan(stations, 600).stops), 3)
        self.assertEqual(
            [s.mile_marker for s in self.merged_plan(stations, 600).stops], [0, 201]
        )

    def test_keeps_cheapest_station_in_each_stretch(self):
        stations = [
            at(0, "3.60"),
            at(100, "3.50"),
            at(110, "3.20"),
            at(120, "3.40"),
            at(400, "3.30"),
            at(410, "3.00"),
        ]

        result = self.merged_plan(stations, 800)

        self.assertEqual([s.mile_marker for s in result.stops], [0, 110, 410])

    def test_always_keeps_the_station_at_the_start(self):
        # Dropping it would charge the first mile at the cheaper price ahead.
        stations = [at(0, "3.40"), at(12, "3.08")]

        result = self.merged_plan(stations, 95)

        self.assertEqual(result.stops[0].mile_marker, 0)
        self.assertEqual(result.starting_gallons, Decimal("0.000"))

    def test_still_covers_the_whole_trip(self):
        stations = [at(0, "3.24"), at(1, "3.10"), at(300, "2.90"), at(310, "3.30")]

        self.assertEqual(self.merged_plan(stations, 700).total_gallons, Decimal("70.000"))

    def test_falls_back_to_all_stations_when_merging_breaks_reachability(self):
        # Keeping only the cheaper station at mile 0 leaves a 510-mile gap;
        # the station at mile 20 is needed to bridge it.
        stations = [at(0, "3.00"), at(20, "3.50"), at(510, "3.00")]

        result = self.merged_plan(stations, 900)

        self.assertIn(20, [s.mile_marker for s in result.stops])

    def test_zero_disables_merging(self):
        stations = [at(0, "3.24"), at(1, "3.10")]

        self.assertEqual(len(self.merged_plan(stations, 300, merge_within_miles=0).stops), 2)


class OptimalityTests(SimpleTestCase):
    """Compare the greedy plan with an exact linear-programming solution."""

    def test_matches_linear_program_on_random_trips(self):
        rng = random.Random(42)
        feasible = 0
        for trial in range(300):
            total = rng.uniform(50, 2500)
            count = rng.randint(1, 25)
            miles = sorted([0.0] + [rng.uniform(0, total) for _ in range(count - 1)])
            stations = [
                at(round(m, 2), f"{rng.uniform(2.5, 5.0):.3f}", opis_id=k)
                for k, m in enumerate(miles)
            ]

            optimum = _linear_program_cost(stations, total)
            with self.subTest(trial=trial):
                if optimum is None:
                    with self.assertRaises(FuelRangeExceeded):
                        plan(stations, total)
                    continue
                feasible += 1
                result = plan(stations, total)
                # Each stop rounds gallons and cents, so allow a cent per stop.
                tolerance = 0.01 * (len(result.stops) + 1)
                self.assertAlmostEqual(float(result.total_cost), optimum, delta=tolerance)

                # Merging only removes options, so it can never beat the optimum.
                merged = plan_fuel_stops(
                    stations, total, max_range_miles=RANGE, mpg=MPG, merge_within_miles=25
                )
                merged_tolerance = 0.01 * (len(merged.stops) + 1)
                self.assertGreaterEqual(float(merged.total_cost), optimum - merged_tolerance)

        self.assertGreater(feasible, 100, "too few feasible trips to be meaningful")


def _linear_program_cost(stations: list[StationOnRoute], total: float) -> float | None:
    """Minimum cost via LP, or None if the trip is infeasible.

    Variable x_i is miles of fuel bought at station i, with stations sorted by
    mile and the first one at the start. The tank starts empty.
    """
    stations = [s for s in stations if s.mile_marker < total]
    assert stations[0].mile_marker == 0
    n = len(stations)
    miles = np.array([s.mile_marker for s in stations])
    prices = np.array([float(s.station.price) for s in stations]) / MPG
    bought_by = np.tril(np.ones((n, n)))  # Row k sums purchases at stations 0..k.

    # Fuel bought before each next station, and before the finish, covers the
    # distance to it: -sum(x_0..x_k) <= -next_mile.
    next_miles = np.append(miles[1:], total)
    # The tank never holds more than its capacity: sum(x_0..x_k) - mile_k <= RANGE.
    a_ub = np.vstack([-bought_by, bought_by])
    b_ub = np.concatenate([-next_miles, miles + RANGE])

    result = linprog(prices, A_ub=a_ub, b_ub=b_ub, bounds=(0, None), method="highs")
    return float(result.fun) if result.status == 0 else None
