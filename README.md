# Fuel Route Optimizer API

[![CI](https://github.com/Hammad7106/fuel-route-optimizer/actions/workflows/ci.yml/badge.svg)](https://github.com/Hammad7106/fuel-route-optimizer/actions/workflows/ci.yml)

A Django REST API that takes a start and finish location in the USA and returns
the driving route, the cheapest places to refuel along it for a vehicle with a
500-mile range, and the total fuel cost at 10 MPG.

- **One routing API call per trip.** Locations are geocoded locally, and repeat
  trips and the map page are served from cache.
- **Fast.** About 1–1.5s for a new trip (nearly all of it the routing API), and
  ~10–100 ms once the route is cached. Planning itself takes about 20 ms or
  less, even coast to coast.
- **Provably cheapest plan.** The fuel planner is tested against an exact
  linear-programming solver on 300 random trips.

## Quick start

```bash
cp .env.example .env
docker compose up --build
```

Full instructions, running without Docker, and troubleshooting:
**[HOW_TO_RUN.md](HOW_TO_RUN.md)**.

Then try it:

| | |
|---|---|
| **Swagger UI** | http://localhost:8000/api/docs/: open `POST /api/route/`, *Try it out*, pick an example, *Execute* |
| **Map** | http://localhost:8000/api/route/map/?start=Dallas,%20TX&finish=Denver,%20CO |
| **Admin** | http://localhost:8000/admin/: `admin` / `change-me`, to browse and filter the stations |
| **Postman** | *Import* → *Link* → `http://localhost:8000/api/schema/` |
| **curl** | `curl -X POST localhost:8000/api/route/ -H "Content-Type: application/json" -d '{"start": "Dallas, TX", "finish": "Denver, CO"}'` |

On start, the container loads the 6,620 fuel stations (about 1s) and then serves
with gunicorn. No API key is needed.

## Design at a glance

Diagrams of the components, startup, request flow and code structure are in
**[ARCHITECTURE.md](ARCHITECTURE.md)**.

```
"Dallas, TX" ─┐
              ├─ resolve locally ── place index (183k US places, offline)
"Denver, CO" ─┘
       │
       ▼
  OSRM route ─────────────────────── the only external call; cached 24h
       │
       ▼
  stations along the route ───────── KD-tree over the route, 10-mile corridor
       │
       ▼
  cheapest fuel plan ─────────────── exact greedy algorithm, 500 mi, 10 MPG
       │
       ▼
  JSON response + map page
```

| Decision | Why |
|---|---|
| **Geocode stations offline** against Census + GeoNames data | The price file has no coordinates. Geocoding 6,600 stations per request (or at all, through an API) would break the "few API calls" requirement. |
| **Resolve start and finish locally** (`"City, ST"` or `"lat,lng"`) | Keeps every trip at exactly one external call |
| **OSRM** public server | Free, no key, one call returns both the road geometry and the distance. Configurable (`OSRM_BASE_URL`) for a self-hosted server. |
| **KD-tree on 3D unit vectors** to match stations to the road | All 6,620 stations matched in one vectorized query (~17 ms coast to coast), with exact distances on the sphere |
| **Greedy "gas station problem" algorithm** | Provably optimal for a fixed route, and linear time |
| **Cache the route, not the answer** | Saves the API call while still using current fuel prices |
| **`Decimal` money**, strings in JSON | Exact to the cent |

## API

### `POST /api/route/`

`start` and `finish` accept `"City, ST"` or `"lat,lng"`.

```json
{"start": "Dallas, TX", "finish": "Denver, CO"}
```

Response (shortened):

```json
{
  "start":  {"label": "Dallas, TX", "latitude": 32.79333, "longitude": -96.76651},
  "finish": {"label": "Denver, CO", "latitude": 39.76185, "longitude": -104.88111},
  "distance_miles": 779.4,
  "duration_hours": 14.5,
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
  start (see [Assumptions](#assumptions-and-trade-offs)).

### `GET /api/route/map/?start=…&finish=…`

The same plan on a Leaflet/OpenStreetMap map, with the route, numbered stops
and per-stop gallons and cost. It reuses the cached route, so it makes no
extra routing call. `map_url` in the API response links to it.

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

## How it works

### 1. Fuel station data

The price file has no coordinates, only each station's city and state, so
stations are geocoded **offline, once**, against a local index of US places.
`python manage.py load_stations` (about 1s, run on container start) cleans and
loads the file:

| Step | Rows |
|---|---|
| Read from `data/fuel_prices.csv` | 8,151 |
| Canadian stations excluded (outside service area) | 620 |
| Duplicate station IDs merged, keeping the **lowest** price | 905 |
| Not geocoded (reported, skipped; listed with `-v 2`) | 6 |
| **Loaded** | **6,620** |

The place index, `data/us_places.csv.gz` (183k places), is built by
`python manage.py build_places` from public datasets, most trusted first:

1. [US Census Gazetteer](https://www.census.gov/geographies/reference-files/time-series/geo/gazetteer-files.html), places (public domain)
2. US Census Gazetteer, county subdivisions, for townships such as Mahwah, NJ
3. [GeoNames](https://www.geonames.org/) populated places (CC BY 4.0), for
   unincorporated truck-stop towns such as Breezewood, PA

It is committed, so it only needs rebuilding to refresh the data. Names are
matched ignoring case, spacing, punctuation and accents, with common
abbreviations expanded ("Mc Calla" = "McCalla", "St." = "Saint").

### 2. Routing

Each new trip makes **one** OSRM `route` request for the full road geometry and
distance, with a 10s timeout. Routes are cached for 24h, keyed by coordinates
rounded to ~11 m.

The cache is shared by all gunicorn workers; with a per-worker cache, a repeat
trip or the map page landing on another worker would call the API again. The
default is a file cache shared within the container. Set
`CACHE_URL=rediscache://…` to share it across containers.

The place and station indexes load once at startup (`config/wsgi.py` with
gunicorn `--preload`), so no request pays the ~0.8s to build them. The routing
client sits behind a `RoutingProvider` protocol, so another provider (a
self-hosted OSRM, GraphHopper, or a test fake) is a drop-in class.

### 3. Stations along the route

A station is on the route when it is within `STATION_SEARCH_RADIUS_MILES`
(default 10) of the road. Each one gets a **mile marker** (how far into the trip
it is) and its **off-route distance**.

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

### 4. Choosing fuel stops

The route is fixed and fuel can be bought in any amount, so this is the "gas
station problem", which has an exact greedy solution:

> At each station, if a cheaper station is within range, buy just enough to
> reach it. Otherwise fill up (or buy just enough to finish) and continue to
> the cheapest station within range.

Optimality is tested, not just claimed: `OptimalityTests` solves 300 random
trips as a linear program with SciPy and checks the planner matches to the
cent. A deliberately broken planner (always fill up) fails 213 of them.

The exact plan can include stops no driver would make, such as 0.12 gallons a
mile before a station 14¢ cheaper. So before planning, only the cheapest
station in each 25-mile stretch is kept (`FUEL_STOP_MERGE_MILES`; `0` turns this
off). The station at the start is always kept, and if merging would leave a
gap beyond the range, all stations are used. Merging only removes options, so
it can never undercut the true optimum; the tests check this too.

| Trip | Stops (exact → merged) | Fuel cost (exact → merged) |
|---|---|---|
| Dallas → Denver (779 mi) | 5 → 5 | $213.29 → $213.29 |
| New York → Los Angeles (2,810 mi) | 18 → 16 | $852.61 → $852.80 |
| Chicago → Milwaukee (95 mi) | 2 → 2 | $29.63 → $29.63 |
| Seattle → Miami (3,303 mi) | 20 → 17 | $1,026.92 → $1,027.18 |

## Assumptions and trade-offs

The main ones are below. All 18, each with an example, are in
**[ASSUMPTIONS.md](ASSUMPTIONS.md)**.

| Assumption | Why | Effect |
|---|---|---|
| The vehicle fills up at the start and arrives empty | The total then covers exactly the fuel the trip uses (miles ÷ MPG). Starting full would make trips under 500 miles cost $0. | If the first station is past the start, the fuel to reach it is charged at that station's price (`fuel_before_first_stop`). |
| Stations are placed at their city's location | The data has no coordinates | Accurate to a few miles: enough to tell whether a station is on the route, but all stations in a city share one point. |
| Detours to stations (up to 10 mi off the road) are free | Most are 1–3 mi off; price differences matter more | A station slightly off the road may be chosen over one on it |
| Stops cost nothing beyond fuel | The assignment asks for the cheapest fuel | Some plans still include small purchases; merging nearby stations removes the worst of them |
| The public OSRM server | Free and keyless, as the assignment asks | Fair use only, with no uptime guarantee; mitigated by caching and a configurable URL |

## What I'd do next in production

- **Geocode each station's address** (e.g. "I-44, EXIT 283") once, offline, for
  exact positions instead of city centres.
- **Add a per-stop cost** to the planner (a dynamic-programming formulation),
  trading a few cents for fewer stops.
- **Count detours** by adding each station's off-route distance to its effective price.
- **Self-host OSRM and use Redis** for the shared cache: both are configuration
  changes (`OSRM_BASE_URL`, `CACHE_URL`).
- **Postgres** instead of SQLite; `load_stations` already replaces the table atomically.
- Rate limiting and authentication if the API were public.

## Development

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py load_stations
python manage.py ensure_superuser   # admin user from .env
python manage.py runserver
python manage.py test               # 103 tests; OSRM is faked, no network needed
```

CI runs the tests and a Docker smoke test (build, start, check that stations
loaded and docs are served) on every push.

### Configuration

All settings come from the environment or `.env` (see `.env.example`):

| Variable | Default | |
|---|---|---|
| `DJANGO_SECRET_KEY` | (required) | |
| `OSRM_BASE_URL` | `https://router.project-osrm.org` | Routing server |
| `ROUTING_TIMEOUT_SECONDS` | `10` | |
| `VEHICLE_MAX_RANGE_MILES` | `500` | |
| `VEHICLE_MPG` | `10` | |
| `STATION_SEARCH_RADIUS_MILES` | `10` | How far off the road a station may be |
| `FUEL_STOP_MERGE_MILES` | `25` | Keep the cheapest station per stretch; `0` to disable |
| `ROUTE_CACHE_TIMEOUT` | `86400` | Seconds |
| `CACHE_URL` | file cache in `.cache/django` | e.g. `rediscache://redis:6379/0` |
| `DJANGO_SUPERUSER_USERNAME` / `_PASSWORD` | (unset) | Admin user created on start if missing; `.env.example` sets `admin` / `change-me` |

### Project layout

```
config/                 Settings, root URLs, WSGI (index warm-up)
routing/
  views.py              Thin API and map views
  admin.py              Unfold admin: read-only stations, state and price filters
  serializers.py        Request validation and response shape
  errors.py             One error format for every error
  openapi.py            Swagger / OpenAPI documentation
  services/
    trip_planner.py     Ties the steps below together
    locations.py        "City, ST" / "lat,lng" → coordinates
    geocoding.py        Offline place index
    routing_client.py   OSRM client + shared cache
    route_stations.py   Stations along the route (KD-tree)
    fuel_planner.py     Cheapest fuel plan
  management/commands/  build_places, load_stations, ensure_superuser
  templates/            Map page
data/                   Fuel price CSV and the US place index
```
