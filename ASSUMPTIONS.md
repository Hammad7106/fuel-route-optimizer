# Assumptions

The assignment leaves several details open. These are the choices made, why,
and what each one means in practice. Numbers are from the real data and the
live routing API.

## Vehicle and fuel

### 1. The vehicle fills up at the start and arrives with an empty tank

The total cost then covers exactly the fuel the trip uses: miles ÷ 10 MPG.

> **Example:** Dallas, TX → Denver, CO is 779.4 miles, so the plan always buys
> **77.9 gallons**, for **$213.29**.

*Alternative rejected:* starting with a free full tank would make every trip
under 500 miles cost $0, which doesn't answer "how much will this trip cost?".

### 2. If there's no station at the start, the fuel to reach the first station is charged at that station's price

This happens when the start is raw coordinates away from any town. The response
shows it separately as `fuel_before_first_stop`.

> **Example:** a start 30 miles before the first station, priced at $3.00/gal:
> 3 gallons are charged at $3.00 = $9.00, as if bought there.

When the start is a city, its own stations sit right at mile 0, so this is zero.

### 3. 500-mile range means a 50-gallon tank

Range ÷ MPG = 500 ÷ 10. Both are settings (`VEHICLE_MAX_RANGE_MILES`, `VEHICLE_MPG`).

### 4. Fuel can be bought in any amount, at the listed retail price

There's no minimum purchase, and price is per gallon with no fees.

## Data

### 5. Stations are placed at the centre of their town

The price file has city and state but no coordinates, so each station is given
its town's location from US Census and GeoNames data.

> **Example:** every Dallas station is at (32.793, -96.767), so in the API they
> all show `mile_marker: 0` and `off_route_miles: 0` on a trip starting in Dallas.

This is accurate to a few miles: enough to tell whether a station is on the route,
but within one city the plan can't tell which station is closer to the highway.
99.9% of US stations are matched; 6 are skipped and listed by
`load_stations -v 2` (e.g. "S Coffeyville, OK").

### 6. When a station appears more than once, its lowest price is used

905 rows are duplicates of the same station ID, often with different prices.
A driver minimizing cost would pay the lowest one.

> **Example:** a station listed at $3.90, $3.40 and $3.70 is loaded once, at $3.40.

### 7. USA only

620 Canadian stations are excluded, and locations outside the US are rejected.

> **Example:** `"Toronto, ON"` → 400 `location_not_found`.

### 8. Prices are a snapshot

Prices come from `data/fuel_prices.csv` and are reloaded on every start. To
update them, replace the file and restart.

## Route and stations

### 9. The route is the one the routing service chooses (OSRM's fastest route)

The plan doesn't reroute to reach cheaper stations elsewhere; that would need
more routing calls, against the "one call is ideal" requirement.

### 10. A station is "on the route" if it's within 10 miles of the road

Town centres can be a few miles from the highway exit, so the corridor is wide
enough to catch real highway stops (`STATION_SEARCH_RADIUS_MILES`).

> **Example:** on Dallas → Denver, Raceway in Bridgeport, TX is 9.6 miles from the
> road and counts; a station 15 miles away doesn't. Most stations used are
> 1–3 miles off the road.

### 11. Detours to stations are free

The miles from the road to a station aren't added to its cost.

> **Example:** the 9.6-mile detour to Bridgeport isn't priced in. With most
> stations 1–3 miles off the road, price differences matter far more.

### 12. A station's position along the trip is the nearest point on the road

Its `mile_marker` is how far into the trip that point is.

## Planning

### 13. "Optimal" means the lowest total fuel cost

The plan is the provably cheapest for the route, tested against an exact
linear-programming solver on 300 random trips.

### 14. Stops cost nothing beyond fuel, so a plan may include small purchases

Buying just enough to reach a slightly cheaper station is cheaper, even if
it's only a little fuel.

> **Example:** New York → Los Angeles buys **0.12 gallons ($0.40)** in Jersey City
> to reach a station 1 mile ahead that is 14¢/gal cheaper.

To limit this, only the cheapest station in each 25-mile stretch is considered
(`FUEL_STOP_MERGE_MILES`): New York → Los Angeles goes from 18 to 16 stops for
$0.19 more. Removing small purchases entirely would need a cost per stop,
listed in the README under next steps.

### 15. When prices tie, fewer stops win

> **Example:** three stations at $3.00 within reach: the plan fills up once
> rather than stopping at each.

### 16. Trips that can't be completed are errors, not partial plans

> **Example:** a 600-mile stretch with no station → 422 `fuel_range_exceeded`:
> "No fuel station between mile 100 and mile 700, which is beyond the vehicle's
> 500-mile range."

## Service

### 17. The public OSRM server is good enough for this assignment

It's free and needs no key, but it's fair-use only with no uptime guarantee.
Routes are cached for 24 hours, and `OSRM_BASE_URL` can point at a self-hosted
server.

### 18. Locations are `"City, ST"` or `"lat,lng"`

Street addresses aren't supported. Resolving them would need a geocoding API,
which means an extra call on every request.

> **Examples:** `"Dallas, TX"`, `"new york, ny"`, `"Chicago, IL, USA"` and
> `"41.8781,-87.6298"` work; `"Chicago"` (no state) and `"Chicago, Illinois"`
> return a 400 explaining the expected format.
