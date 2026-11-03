# Fuel Route Optimizer API

A Django REST API that takes a start and finish location in the USA and returns
the driving route, the most cost-effective fuel stops along it (500-mile range),
and the total fuel cost (10 MPG).

One request, one call to the routing API, and a typical response in **~10–100 ms**
once the route is cached (about 1–1.5s on a new trip, nearly all of it the routing API).

## Tech stack

- Python 3.13, Django 6.1, Django REST Framework
- [OSRM](https://project-osrm.org/) for routing (public server, no API key)
- Fuel prices from `data/fuel_prices.csv`

## Getting started

### 1. Configure environment

```bash
cp .env.example .env
```

Set `DJANGO_SECRET_KEY` in `.env`. Routing needs no API key.

### 2a. Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py load_stations
python manage.py runserver
```

The Docker image runs `migrate` and `load_stations` on start.

### 2b. Run with Docker

```bash
docker compose up --build
```

### 3. Check it is running

```bash
curl http://localhost:8000/api/health/
```

## API

### Try it

- **Swagger UI:** http://localhost:8000/api/docs/. Open `POST /api/route/`,
  click *Try it out*, pick an example (Dallas → Denver, New York → Los Angeles,
  coordinates, or an error case) and *Execute*.
- **Postman:** *Import* → *Link* → `http://localhost:8000/api/schema/`, which
  creates a ready-made collection from the OpenAPI schema.
- **Map:** http://localhost:8000/api/route/map/?start=Dallas,%20TX&finish=Denver,%20CO

### `POST /api/route/`

```bash
curl -X POST http://localhost:8000/api/route/ \
     -H "Content-Type: application/json" \
     -d '{"start": "Dallas, TX", "finish": "Denver, CO"}'
```

`start` and `finish` accept `"City, ST"` or `"lat,lng"`. Response (shortened):

```json
{
  "start":  {"label": "Dallas, TX", "latitude": 32.79333, "longitude": -96.76651},
  "finish": {"label": "Denver, CO", "latitude": 39.76185, "longitude": -104.88111},
  "distance_miles": 779.4,
  "duration_hours": 11.8,
  "total_gallons": "77.938",
  "total_fuel_cost": "213.29",
  "fuel_before_first_stop": {"gallons": "0.000", "cost": "0.00"},
  "fuel_stops": [
    {
      "opis_id": 72773, "name": "RaceTrac #2626", "address": "I-20 Exit 472",
      "city": "Dallas", "state": "TX", "latitude": 32.79333, "longitude": -96.76651,
      "mile_marker": 0.0, "off_route_miles": 0.0,
      "price_per_gallon": "2.864", "gallons": "7.310", "cost": "20.94"
    }
  ],
  "route": {"type": "LineString", "coordinates": [[-96.76651, 32.79333], "..."]},
  "map_url": "http://localhost:8000/api/route/map/?start=Dallas%2C+TX&finish=Denver%2C+CO"
}
```

- Money and gallons are strings, so they keep exact decimal precision.
- `route` is GeoJSON, simplified for display (New York → Los Angeles: 35k → 2.6k
  points, 868 KB → 59 KB). Calculations use the full route.
- `fuel_before_first_stop` is non-zero only when the first station is past the
  start (see the assumptions below).

### `GET /api/route/map/?start=…&finish=…`

The same plan on a Leaflet/OpenStreetMap map: route, numbered stops, and
per-stop gallons and cost. It reuses the cached route, so it makes no extra
routing call. `map_url` in the API response links to it.

### Errors

Every error has the same shape:

```json
{"error": {"code": "location_not_found", "message": "Could not find 'Atlantis, TX'. ..."}}
```

| Status | `code` | When |
|---|---|---|
| 400 | `invalid_request` | Missing or invalid fields (details in `fields`) |
| 400 | `location_not_found` | A location can't be resolved to a US place |
| 422 | `route_not_found` | No drivable route (e.g. Honolulu → Los Angeles) |
| 422 | `fuel_range_exceeded` | A stretch with no station within the vehicle's range |
| 503 | `routing_unavailable` | The routing service failed or timed out |

### Other endpoints

- `GET /`: endpoint index
- `GET /api/health/`: status, stations loaded, routing provider
- `GET /api/docs/`: Swagger UI; `GET /api/schema/`: OpenAPI 3 schema

## Fuel station data

The price file has no coordinates, only each station's city and state, so
stations are geocoded **offline, once**, against a local index of US places.
No geocoding API is called, at load time or per request.

`python manage.py load_stations` (about 1s) cleans and loads the file:

| Step | Rows |
|---|---|
| Read from `data/fuel_prices.csv` | 8,151 |
| Canadian stations excluded (outside service area) | 620 |
| Duplicate station IDs merged, keeping the **lowest** price | 905 |
| Not geocoded (reported, skipped) | 6 |
| **Loaded** | **6,620** |

Run with `-v 2` to list the cities that could not be geocoded.

Stations are placed at their city's location. That is accurate to a few
miles, which is enough to decide whether a station is on a route, since truck
stops sit on the highway at the town they're named for.

### Place index

`data/us_places.csv.gz` (183k places) is built by `python manage.py build_places`
from public datasets, most trusted first:

1. [US Census Gazetteer](https://www.census.gov/geographies/reference-files/time-series/geo/gazetteer-files.html), places (public domain)
2. US Census Gazetteer, county subdivisions, for townships such as Mahwah, NJ
3. [GeoNames](https://www.geonames.org/) populated places (CC BY 4.0), for
   unincorporated truck-stop towns such as Breezewood, PA

The output is committed, so this only needs re-running to refresh the data.
Names are matched ignoring case, spacing, punctuation and accents, with common
abbreviations expanded ("Mc Calla" = "McCalla", "St." = "Saint").

## Routing

Each new trip makes exactly **one** external API call: an OSRM `route`
request for the full road geometry and distance.

- **Locations** are resolved locally, with no geocoding API. Accepted forms:
  `"City, ST"` (e.g. `"Chicago, IL"`, matched against the place index above)
  or `"lat,lng"` (e.g. `"41.88,-87.63"`).
- **Caching:** routes are cached for `ROUTE_CACHE_TIMEOUT` (24h), keyed by
  coordinates rounded to ~11 m, so repeat trips make no API call (about 1.1s
  becomes about 4ms for New York → Los Angeles). The route is cached rather
  than the final answer, so reloading fuel prices takes effect immediately.
- **Errors:** an unknown location, no drivable route (e.g. Honolulu → Los
  Angeles) and an unavailable provider are distinct errors with clear messages.
- **Swappable provider:** `OSRM_BASE_URL` defaults to the public demo server,
  which is fair-use only. In production, point it at a self-hosted OSRM.
  Callers depend on a `RoutingProvider` protocol, so another provider (e.g.
  GraphHopper) is a drop-in class.

The cache must be shared by all gunicorn workers; otherwise a repeat trip or
the map page landing on another worker calls the API again. The default is a
file cache shared within the container. Set `CACHE_URL=rediscache://…` to
share it across containers. Repeat requests take ~10–100 ms on any worker.

The place and station indexes load once at startup (`config/wsgi.py`, with
gunicorn `--preload`), so no request pays the ~0.8s to build them.

## Stations along the route

Stations count as on the route when they are within
`STATION_SEARCH_RADIUS_MILES` (default 10) of the road. Each one gets a
**mile marker** (how far into the trip it is) and its **off-route distance**.

- All stations are held in memory once per worker (6,620 stations, ~50 ms
  to load).
- Per request, a KD-tree (`scipy.spatial.cKDTree`) is built over the route's
  points, and every station is matched to its nearest point in one vectorized
  query. Points are 3D unit vectors, so distances are exact on the sphere.
- OSRM leaves gaps of up to ~4 miles on straight roads, so the path is filled
  in to at most 0.5 miles between points before matching.

| Trip | Distance | Stations on route | Largest gap | Time |
|---|---|---|---|---|
| New York → Los Angeles | 2,810 mi | 459 | 138 mi | 17 ms |
| Dallas → Denver | 779 mi | 107 | 95 mi | 5 ms |
| Chicago → Milwaukee | 95 mi | 53 | 20 mi | 2 ms |

**Why 10 miles:** station coordinates are city-level, so a truck stop can sit
a few miles from its town's centre point. Stations in the results are a median
of 1–3 miles off the road. A narrower corridor misses real highway stops; a
wider one admits stations needing long detours.

## Choosing fuel stops

With a 500-mile range and 10 MPG (both configurable), the planner picks where
to stop and how much to buy at each stop. The route is fixed and any amount
can be bought, so this is the "gas station problem", which has an exact
greedy solution:

> At each station, if a cheaper station is within range, buy just enough to
> reach it. Otherwise fill up (or buy just enough to finish) and continue to
> the cheapest station within range.

Optimality is tested, not just claimed: `OptimalityTests` solves 300 random
trips as a linear program with SciPy and checks the planner matches to the
cent. A deliberately broken planner (always fill up) fails 213 of them.

**Assumptions**

- The vehicle fills up at the start and arrives with an empty tank, so the
  total covers exactly the fuel used (miles ÷ MPG). If the first station is
  past the start, the fuel to reach it is charged at that station's price.
- Detours to stations off the road (up to 10 miles) are treated as free.
- Stops cost nothing beyond fuel; on price ties the planner prefers fewer stops.
- Money uses `Decimal`, rounded to the cent per stop.

**Avoiding tiny stops.** The exact plan can include stops no driver would make,
such as 0.12 gallons a mile before a station 14¢ cheaper. Before planning,
only the cheapest station in each 25-mile stretch is kept as a candidate
(`FUEL_STOP_MERGE_MILES`; `0` disables it). The station at the start is
always kept, since the vehicle fills up there. If merging would leave a gap
beyond the range, the planner uses all stations instead. Merging only removes
options, so the plan can never undercut the true optimum; the tests check
this too. In practice it costs cents and removes a few stops. Removing small
purchases entirely needs a per-stop cost in the objective (a
dynamic-programming formulation), noted as a possible extension.

| Trip | Stops (exact → merged) | Fuel cost (exact → merged) | Stations + plan |
|---|---|---|---|
| Dallas → Denver (779 mi) | 5 → 5 | $213.29 → $213.29 | 6 ms |
| New York → Los Angeles (2,810 mi) | 18 → 16 | $852.61 → $852.80 | 17 ms |
| Chicago → Milwaukee (95 mi) | 2 → 2 | $29.63 → $29.63 | 2 ms |
| Seattle → Miami (3,303 mi) | 20 → 17 | $1,026.92 → $1,027.18 | ~20 ms |

## Running tests

```bash
python manage.py test
```

## Project layout

```
config/              Django project settings and root URLs
routing/             App: API views, serializers, error format, models
routing/services/    Business logic: trip_planner ties together geocoding,
                     routing, stations along the route and the fuel planner
routing/management/  build_places and load_stations commands
data/                Fuel price CSV and the generated US place index
```
