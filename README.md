# Fuel Route Optimizer API

A Django REST API that takes a start and finish location in the USA and returns
the driving route, the most cost-effective fuel stops along it (500-mile range),
and the total fuel cost (10 MPG).

> Work in progress. The route and fuel-stop endpoints are under construction.

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

The default cache is in-process (`LocMemCache`), so each gunicorn worker has
its own. A shared Redis cache is a one-line settings change.

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

## Running tests

```bash
python manage.py test
```

## Project layout

```
config/              Django project settings and root URLs
routing/             App: API views, models, serializers
routing/services/    Business logic (geocoding, station import, routing, optimizer)
routing/management/  build_places and load_stations commands
data/                Fuel price CSV and the generated US place index
```
