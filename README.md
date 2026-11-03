# Fuel Route Optimizer API

A Django REST API that takes a start and finish location in the USA and returns
the driving route, the most cost-effective fuel stops along it (500-mile range),
and the total fuel cost (10 MPG).

> Work in progress. The route and fuel-stop endpoints are under construction.

## Tech stack

- Python 3.13, Django 6.0, Django REST Framework
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
python manage.py runserver
```

### 2b. Run with Docker

```bash
docker compose up --build
```

### 3. Check it is running

```bash
curl http://localhost:8000/api/health/
```

## Running tests

```bash
python manage.py test
```

## Project layout

```
config/              Django project settings and root URLs
routing/             App: API views, models, serializers
routing/services/    Business logic (routing client, station index, optimizer)
data/                Fuel price CSV
```
