# Architecture

How the Fuel Route Optimizer is put together: the components, what happens at
startup, the path of a request, and where data lives. The diagrams are
[Mermaid](https://mermaid.js.org/) and render on GitHub.

## System overview

```mermaid
flowchart LR
    subgraph Clients
        API_CLIENT["Postman / curl / Swagger UI"]
        BROWSER["Browser"]
    end

    subgraph Container["Docker container"]
        subgraph Django["Django app (gunicorn, 3 workers)"]
            VIEWS["API views<br/>POST /api/route/"]
            MAP["Map page<br/>GET /api/route/map/"]
            DOCS["Swagger UI<br/>/api/docs/"]
            ADMIN["Unfold admin<br/>/admin/"]
            SERVICES["Services<br/>trip_planner"]
        end
        MEMORY[("In-memory indexes<br/>183k places · 6,620 stations")]
        CACHE[("Shared route cache<br/>file cache, 24h")]
        DB[("SQLite<br/>FuelStation table")]
    end

    OSRM["OSRM routing API<br/>router.project-osrm.org"]
    TILES["OpenStreetMap tiles"]

    API_CLIENT --> VIEWS
    API_CLIENT --> DOCS
    BROWSER --> MAP
    BROWSER --> ADMIN
    BROWSER -. "map tiles" .-> TILES
    VIEWS --> SERVICES
    MAP --> SERVICES
    ADMIN --> DB
    SERVICES --> MEMORY
    SERVICES --> CACHE
    SERVICES -- "1 call per new trip" --> OSRM
    MEMORY -. "loaded at startup" .-> DB
```

The only external call on the request path is **one OSRM route request per new
trip**. Everything else (geocoding, station matching, planning) runs on data
already in memory.

## Startup

The fuel price file has no coordinates, so stations are geocoded **once, before
the server accepts requests**, against a committed index of US places.

```mermaid
flowchart TB
    subgraph OneOff["One-off data build (output committed to git)"]
        CENSUS["US Census Gazetteer<br/>places + county subdivisions"]
        GEONAMES["GeoNames<br/>US populated places"]
        BUILD["manage.py build_places"]
        PLACES[("data/us_places.csv.gz<br/>183k places")]
        CENSUS --> BUILD
        GEONAMES --> BUILD
        BUILD --> PLACES
    end

    subgraph Start["Every container start (docker compose up)"]
        MIGRATE["migrate"]
        LOAD["load_stations<br/>drop non-US · merge duplicates · geocode"]
        SUPER["ensure_superuser"]
        GUNICORN["gunicorn --preload"]
        WARM["warm_up()<br/>load place + station indexes"]
        FORK["fork 3 workers<br/>(share the loaded memory)"]
        MIGRATE --> LOAD --> SUPER --> GUNICORN --> WARM --> FORK
    end

    CSV[("data/fuel_prices.csv<br/>8,151 rows")]
    DB[("SQLite<br/>6,620 stations")]
    CSV --> LOAD
    PLACES --> LOAD
    LOAD --> DB
    DB --> WARM
    PLACES --> WARM
```

| Stage | Time | Result |
|---|---|---|
| `load_stations` | ~1s | 8,151 rows → 620 non-US dropped, 905 duplicates merged (lowest price kept), 6 not geocoded → **6,620 stations** |
| `warm_up()` | ~0.8s | Place index and station index in memory before the first request |

## Request flow: `POST /api/route/`

```mermaid
sequenceDiagram
    autonumber
    actor Client
    participant View as TripPlanView
    participant Planner as trip_planner
    participant Places as PlaceIndex<br/>(in memory)
    participant Router as CachedRoutingProvider
    participant Cache as Route cache
    participant OSRM as OSRM API
    participant Stations as StationIndex<br/>(KD-tree)
    participant Fuel as fuel_planner

    Client->>View: {"start": "Dallas, TX", "finish": "Denver, CO"}
    View->>View: validate (TripRequestSerializer)
    View->>Planner: plan_trip(start, finish)
    Planner->>Places: resolve "Dallas, TX", "Denver, CO"
    Places-->>Planner: coordinates (no API call)
    Planner->>Router: route(start, finish)
    Router->>Cache: get(rounded coordinates)
    alt cache hit
        Cache-->>Router: Route
    else cache miss
        Router->>OSRM: GET /route/v1/driving/... (the one external call)
        OSRM-->>Router: road geometry + distance
        Router->>Router: simplify geometry for display
        Router->>Cache: set(Route, 24h)
    end
    Router-->>Planner: Route (779.4 mi)
    Planner->>Stations: along(route, 10 mi)
    Stations-->>Planner: 107 stations with mile markers
    Planner->>Fuel: plan_fuel_stops(stations, 779.4 mi, 500 mi, 10 MPG)
    Fuel-->>Planner: 5 stops, 77.9 gal, $213.29
    Planner-->>View: TripPlan
    View-->>Client: 200 JSON (stops, total cost, GeoJSON route, map_url)
```

The map page (`GET /api/route/map/`) runs the same `plan_trip`. Its route is
already cached, so it makes no OSRM call.

| Step | Time (New York → Los Angeles) |
|---|---|
| Resolve locations | < 1 ms |
| OSRM route (new trip) | ~1–1.5 s |
| OSRM route (cached) | 0, read from cache |
| Stations along the route (459 found) | ~17 ms |
| Fuel plan | < 1 ms |
| **Total** | ~1.5 s new · **~10–100 ms** cached |

## Inside the fuel planner

At each candidate station the planner asks one question. This greedy rule is
provably optimal for a fixed route, and the tests check it against an exact
linear-programming solver.

```mermaid
flowchart TB
    START(["Arrive at a station<br/>with fuel F"]) --> Q1{"Cheaper station<br/>within 500 mi?"}
    Q1 -- "yes" --> BUY1["Buy just enough<br/>to reach it"]
    BUY1 --> NEXT1["Drive to that station"]
    NEXT1 --> START
    Q1 -- "no" --> Q2{"Finish within<br/>500 mi?"}
    Q2 -- "yes" --> BUY2["Buy just enough<br/>to finish"]
    BUY2 --> DONE(["Arrive empty"])
    Q2 -- "no" --> FILL["Fill the tank"]
    FILL --> NEXT2["Drive to the cheapest<br/>station within reach"]
    NEXT2 --> START
```

Before planning, only the cheapest station in each 25-mile stretch is kept, so
plans avoid tiny stops. A stretch longer than 500 miles with no station returns
`422 fuel_range_exceeded`.

## Code structure

Views stay thin; all logic lives in plain-Python services, each testable on its own.

```mermaid
flowchart TB
    subgraph Web["HTTP layer (routing/)"]
        V["views.py"]
        S["serializers.py"]
        E["errors.py<br/>one error format"]
        O["openapi.py<br/>Swagger docs"]
        A["admin.py<br/>Unfold, read-only"]
    end

    subgraph Svc["Services (routing/services/)"]
        TP["trip_planner.py"]
        LOC["locations.py<br/>City, ST / lat,lng"]
        GEO["geocoding.py<br/>PlaceIndex"]
        RC["routing_client.py<br/>OSRM + cache"]
        GM["geometry.py<br/>line simplification"]
        RS["route_stations.py<br/>KD-tree matching"]
        FP["fuel_planner.py<br/>cheapest plan"]
        EX["exceptions.py"]
    end

    subgraph Data["Data (routing/)"]
        M["models.py<br/>FuelStation"]
        CMD["management/commands<br/>build_places · load_stations"]
    end

    V --> S
    V --> TP
    V --> E
    O -. "documents" .-> V
    TP --> LOC --> GEO
    TP --> RC --> GM
    TP --> RS --> M
    TP --> FP
    LOC -. "raises" .-> EX
    RC -. "raises" .-> EX
    FP -. "raises" .-> EX
    E -. "maps to HTTP" .-> EX
    A --> M
    CMD --> M
    CMD --> GEO
```

| Module | Responsibility |
|---|---|
| `trip_planner` | The single entry point: resolve → route → stations → plan |
| `locations` / `geocoding` | Turn `"City, ST"` or `"lat,lng"` into coordinates, offline |
| `routing_client` | One OSRM call, timeouts, error mapping, shared cache; swappable behind a `RoutingProvider` protocol |
| `route_stations` | Stations within 10 mi of the road, with mile markers |
| `fuel_planner` | Where to stop and how much to buy; exact `Decimal` money |
| `errors` | Every error, whether validation, planning or HTTP, as `{"error": {"code", "message"}}` |

## Where data lives

| Data | Stored in | Lifetime |
|---|---|---|
| Fuel prices (raw) | `data/fuel_prices.csv` (git) | Permanent: the source of truth |
| US place index | `data/us_places.csv.gz` (git) | Permanent; rebuilt with `build_places` |
| Geocoded stations | SQLite, `FuelStation` table | Rebuilt from the CSV on every start |
| Place + station indexes | Process memory, shared by workers | Until the server restarts |
| Routes from OSRM | Shared file cache (`CACHE_URL`) | 24 hours |
| Admin user | SQLite | Recreated on start from `DJANGO_SUPERUSER_*` |

## Errors

```mermaid
flowchart LR
    REQ["Request"] --> VAL{"Valid fields?"}
    VAL -- "no" --> E400A["400 invalid_request"]
    VAL -- "yes" --> LOCQ{"Locations found?"}
    LOCQ -- "no" --> E400B["400 location_not_found"]
    LOCQ -- "yes" --> OSRMQ{"OSRM ok?"}
    OSRMQ -- "down / timeout" --> E503["503 routing_unavailable"]
    OSRMQ -- "no road" --> E422A["422 route_not_found"]
    OSRMQ -- "yes" --> RANGEQ{"Every gap<br/>within 500 mi?"}
    RANGEQ -- "no" --> E422B["422 fuel_range_exceeded"]
    RANGEQ -- "yes" --> OK["200 fuel plan"]
```

## Scaling beyond one container

| Today | Production | Change needed |
|---|---|---|
| Public OSRM server | Self-hosted OSRM | `OSRM_BASE_URL` |
| File cache, shared within one container | Redis, shared by all containers | `CACHE_URL=rediscache://…` |
| SQLite, rebuilt on start | Postgres | `DATABASE_URL`; `load_stations` already replaces the table atomically |
| City-level station positions | Address-level positions | Geocode station addresses once, offline |
