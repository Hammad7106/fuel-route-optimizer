# Fuel Route Optimizer API

A Django REST API that takes a start and finish location in the USA and returns
the driving route, the most cost-effective fuel stops along it (500-mile range),
and the total fuel cost (10 MPG).

> Work in progress. The route and fuel-stop endpoints are under construction.

## Tech stack

- Python 3.13, Django 6.1, Django REST Framework
- [OpenRouteService](https://openrouteservice.org/) for routing (free tier)
- Fuel prices from `data/fuel_prices.csv`

## Getting started

### 1. Configure environment

```bash
cp .env.example .env
```

Set `DJANGO_SECRET_KEY` and `ORS_API_KEY` (free key from
https://openrouteservice.org/dev/#/signup) in `.env`.

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
