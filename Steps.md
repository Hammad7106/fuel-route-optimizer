# Fuel Route Optimizer — Plan & Steps

## Goal

`POST /api/route/` takes a start and finish location in the USA and returns:

- the driving route (GeoJSON + a map link)
- the most cost-effective fuel stops along it (500-mile max range)
- the total fuel cost (10 MPG)

Constraints: latest stable Django, fast responses, one call to the routing API
per request (two or three at most).

## Key insight

`data/fuel_prices.csv` (~8,150 rows) has **no coordinates** — only address,
city and state. Stations must be geocoded **once, offline**, so requests never
geocode stations. Start/finish are geocoded locally from the same city dataset,
which keeps each request to a single routing API call.

## Done

- [x] Django 6.1.2 + DRF project scaffold with `/api/health/`
- [x] Virtualenv and settings via `.env`
- [x] Dockerfile and docker-compose with healthcheck
- [x] GitHub repo linked

## Steps

### 0. Finish setup
- [x] Restart Docker Desktop, run `docker compose up --build`, confirm `/api/health/`
- [x] ~~ORS API key~~: switched to OSRM (no key needed; ORS was down for maintenance)

### 1. Geocode fuel stations (unblocks everything) ✅
- [x] `FuelStation` model (name, address, city, state, price, lat, lon)
- [x] `build_places`: Census places + county subdivisions + GeoNames → `data/us_places.csv.gz`
- [x] `load_stations` management command (offline, ~1s, runs on container start)
  - [x] Exclude Canadian stations (620 rows)
  - [x] Merge duplicate station IDs, keeping the lowest price (905 rows)
  - [x] Geocode City + State against the place index (99.9% matched)
  - [x] Report unmatched rows (6, listed with `-v 2`)
- [x] Commit the place index (instead of the DB) so the load is reproducible
- [x] Tests: normalization, name variants, source priority, dedupe, command

### 2. Routing client ✅
- [x] One OSRM `route` call per new trip (full GeoJSON geometry + distance)
- [x] Resolve start/finish locally: `"City, ST"` via the place index, or raw `"lat,lng"`
  - No external geocoding fallback, which keeps every trip at exactly 1 API call
- [x] Timeouts and distinct errors: location not found / no route / provider unavailable
- [x] Cache routes for 24h by rounded coordinates (repeat NY→LA: 1.1s → 4ms)
- [x] `RoutingProvider` protocol so the provider is swappable
- [x] Health check reports stations loaded and routing provider
- [x] Tests with OSRM mocked (no network)

### 3. Stations along the route ✅
- [x] Compute cumulative miles along the route geometry (scaled to OSRM's distance)
- [x] Fill in OSRM's long straight-road gaps (up to ~4 mi) to ≤ 0.5 mi between points
- [x] KD-tree over route points; all stations matched in one vectorized query
- [x] Record each station's mile marker and off-route distance
- [x] 10-mile corridor, configurable via `STATION_SEARCH_RADIUS_MILES`
- [x] NY→LA: 459 stations in 17 ms; largest gap 138 mi (well under the 500-mi range)
- [x] Tests on synthetic equator routes (exact expected distances)

### 4. Fuel-stop optimizer
- [ ] Greedy algorithm, 500-mile range, starting with a full tank
  - Cheaper station within reach → buy only enough to get there
  - Otherwise → fill up and go to the cheapest station in range
  - Destination within reach → buy only enough to finish
- [ ] Total cost at 10 MPG
- [ ] Edge cases: short trip (no stops), gap over 500 miles (error)

### 5. API endpoint + map
- [ ] `POST /api/route/` with input validation
- [ ] Response: distance, total cost, gallons, fuel stops, route GeoJSON, `map_url`
- [ ] Leaflet/OpenStreetMap page drawing route and stops (no extra routing call)

### 6. Tests & polish
- [ ] Unit tests for the optimizer (pure logic, no network)
- [ ] Mocked routing client tests
- [ ] README: design decisions, assumptions, how to run
- [ ] Postman collection in the repo
- [ ] Measure and report response times

### 7. Submit
- [ ] Record Loom (≤ 5 min): problem + key insight, Postman demo, code tour
- [ ] Give reviewers access to the private repo (or make it public)
- [ ] Send GitHub link + Loom
