"""Choose where to refuel, and how much to buy, to minimize the cost of a trip.

The route is fixed and fuel can be bought in any amount, which makes this the
classic "gas station problem". It has an exact greedy solution: at each
station, if a cheaper station is within range, buy just enough to reach it;
otherwise fill up (or buy just enough to finish) and continue to the cheapest
station within range. ``test_fuel_planner`` checks the result against a
linear-programming solver on random trips.

Assumptions:

* The vehicle fills up at the start and arrives with an empty tank, so the
  plan pays for exactly the fuel the trip uses. If the first station is past
  the start, the fuel to reach it is charged at that station's price.
* Detours to stations off the road are free, and stops cost nothing beyond
  fuel. When prices tie, the plan prefers fewer stops.

Left alone, the exact plan includes stops no driver would make, such as
buying 0.1 gallons one mile before a station a few cents cheaper. With
``merge_within_miles``, only the cheapest station in each stretch of that
length is considered, so the plan is optimal over those candidates and
costs a few cents more than the theoretical minimum.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from .exceptions import FuelRangeExceeded
from .route_stations import Station, StationOnRoute

CENT = Decimal("0.01")
GALLON_PRECISION = Decimal("0.001")

# Fuel is tracked in miles of range; this absorbs float error in comparisons.
_EPSILON_MILES = 1e-6


@dataclass(frozen=True, slots=True)
class FuelStop:
    station: Station
    mile_marker: float
    off_route_miles: float
    gallons: Decimal
    cost: Decimal


@dataclass(frozen=True, slots=True)
class FuelPlan:
    stops: tuple[FuelStop, ...]
    total_miles: float
    # Fuel used before the first station, when it is past the start.
    starting_gallons: Decimal
    starting_cost: Decimal

    @property
    def total_gallons(self) -> Decimal:
        return self.starting_gallons + sum((s.gallons for s in self.stops), Decimal(0))

    @property
    def total_cost(self) -> Decimal:
        return self.starting_cost + sum((s.cost for s in self.stops), Decimal(0))


def plan_fuel_stops(
    stations: Sequence[StationOnRoute],
    total_miles: float,
    *,
    max_range_miles: float,
    mpg: float,
    merge_within_miles: float = 0.0,
) -> FuelPlan:
    """Return the cheapest refuelling plan for a trip of ``total_miles``.

    ``stations`` are the stations along the route, in any order. Raises
    ``FuelRangeExceeded`` when some stretch has no station within range.
    """
    if total_miles <= _EPSILON_MILES:
        return FuelPlan((), total_miles, Decimal(0), Decimal(0))

    # Stations at the finish are useless: the vehicle arrives empty.
    candidates = sorted(
        (s for s in stations if s.mile_marker < total_miles - _EPSILON_MILES),
        key=lambda s: (s.mile_marker, s.station.price),
    )
    _check_reachable(candidates, total_miles, max_range_miles)

    merged = _cheapest_per_stretch(candidates, merge_within_miles)
    try:
        _check_reachable(merged, total_miles, max_range_miles)
    except FuelRangeExceeded:
        # Merging dropped a station that bridges a long gap; plan without it.
        merged = candidates
    return _build_plan(merged, total_miles, max_range_miles, mpg)


def _build_plan(
    candidates: Sequence[StationOnRoute], total_miles: float, max_range_miles: float, mpg: float
) -> FuelPlan:
    purchases = _greedy_purchases(candidates, total_miles, max_range_miles)

    first = candidates[0]
    starting_gallons = _gallons(first.mile_marker, mpg)
    stops = tuple(
        FuelStop(
            station=stop.station,
            mile_marker=stop.mile_marker,
            off_route_miles=stop.off_route_miles,
            gallons=(gallons := _gallons(miles, mpg)),
            cost=_money(gallons * stop.station.price),
        )
        for stop, miles in purchases
    )
    return FuelPlan(
        stops=stops,
        total_miles=total_miles,
        starting_gallons=starting_gallons,
        starting_cost=_money(starting_gallons * first.station.price),
    )


def _greedy_purchases(
    stations: Sequence[StationOnRoute], total_miles: float, tank_miles: float
) -> list[tuple[StationOnRoute, float]]:
    """Return (station, miles of fuel bought) for each stop, in trip order."""
    next_cheaper = _next_cheaper_indexes(stations)
    purchases: list[tuple[StationOnRoute, float]] = []
    fuel = 0.0  # Miles of range in the tank on arrival at the current station.
    i = 0

    def buy(miles: float) -> None:
        nonlocal fuel
        if miles > _EPSILON_MILES:
            purchases.append((stations[i], miles))
            fuel += miles

    while True:
        current = stations[i]
        reach = current.mile_marker + tank_miles
        cheaper = next_cheaper[i]

        if cheaper is not None and stations[cheaper].mile_marker <= reach:
            # Buy only what it takes to get to the cheaper station.
            target = cheaper
            buy(stations[target].mile_marker - current.mile_marker - fuel)
        elif total_miles <= reach:
            # Nothing cheaper before the finish: buy just enough to arrive empty.
            buy(total_miles - current.mile_marker - fuel)
            return purchases
        else:
            # This is the cheapest fuel in range: fill up, then go to the
            # cheapest station within reach (the furthest one, on ties).
            buy(tank_miles - fuel)
            target = min(
                (j for j in range(i + 1, len(stations)) if stations[j].mile_marker <= reach),
                key=lambda j: (stations[j].station.price, -stations[j].mile_marker),
            )

        fuel -= stations[target].mile_marker - current.mile_marker
        i = target


def _cheapest_per_stretch(
    stations: Sequence[StationOnRoute], stretch_miles: float
) -> list[StationOnRoute]:
    """Group stations into stretches starting at each group's first station, keep the cheapest.

    ``stations`` must be sorted by mile marker. The first station is always
    kept: the vehicle fills up there, so dropping it would price the drive to
    the next station at that station's (possibly lower) price.
    """
    if stretch_miles <= 0 or not stations:
        return list(stations)
    kept: list[StationOnRoute] = [stations[0]]
    group_start = None
    for station in stations[1:]:
        if group_start is None or station.mile_marker - group_start >= stretch_miles:
            group_start = station.mile_marker
            kept.append(station)
        elif station.station.price < kept[-1].station.price:
            kept[-1] = station
    return kept


def _next_cheaper_indexes(stations: Sequence[StationOnRoute]) -> list[int | None]:
    """For each station, the index of the next station ahead with a strictly lower price."""
    result: list[int | None] = [None] * len(stations)
    pending: list[int] = []  # Stations still waiting for a cheaper one; prices increase.
    for j, station in enumerate(stations):
        while pending and stations[pending[-1]].station.price > station.station.price:
            result[pending.pop()] = j
        pending.append(j)
    return result


def _check_reachable(
    stations: Sequence[StationOnRoute], total_miles: float, tank_miles: float
) -> None:
    if not stations:
        raise FuelRangeExceeded("There are no fuel stations along this route.")

    stretch_starts = [0.0] + [s.mile_marker for s in stations]
    stretch_ends = [s.mile_marker for s in stations] + [total_miles]
    for start, end in zip(stretch_starts, stretch_ends, strict=True):
        if end - start > tank_miles + _EPSILON_MILES:
            raise FuelRangeExceeded(
                f"No fuel station between mile {start:,.0f} and mile {end:,.0f}, "
                f"which is beyond the vehicle's {tank_miles:,.0f}-mile range."
            )


def _gallons(miles: float, mpg: float) -> Decimal:
    return Decimal(miles / mpg).quantize(GALLON_PRECISION, rounding=ROUND_HALF_UP)


def _money(amount: Decimal) -> Decimal:
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)
