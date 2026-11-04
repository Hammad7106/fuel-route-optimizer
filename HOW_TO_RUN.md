# How to run

## With Docker (recommended)

**Requires:** [Docker Desktop](https://www.docker.com/products/docker-desktop/) (or Docker Engine with Compose).

```bash
git clone https://github.com/Hammad7106/fuel-route-optimizer.git
cd fuel-route-optimizer
cp .env.example .env
docker compose up --build
```

The first build takes a few minutes. It's ready when the log shows:

```
Loaded 6,620 fuel stations.
Created admin user 'admin'.
[INFO] Booting worker with pid: ...
```

No API key is needed: routing uses the free public OSRM server.

### What to open

| | URL |
|---|---|
| API index | http://localhost:8000/ |
| **Swagger UI** (try the API in the browser) | http://localhost:8000/api/docs/ |
| **Map** of an example trip | http://localhost:8000/api/route/map/?start=Dallas,%20TX&finish=Denver,%20CO |
| **Admin** (user `admin`, password `change-me`) | http://localhost:8000/admin/ |
| Health check | http://localhost:8000/api/health/ |

Stop with `Ctrl+C`, or run `docker compose down` from another terminal.

## Trying the API

### Swagger UI

1. Open http://localhost:8000/api/docs/
2. Click **`POST /api/route/`**, then **Try it out**.
3. Pick an example (Dallas → Denver, New York → Los Angeles, coordinates, or an error case).
4. Click **Execute**.

### curl

```bash
curl -X POST http://localhost:8000/api/route/ \
     -H "Content-Type: application/json" \
     -d '{"start": "Dallas, TX", "finish": "Denver, CO"}'
```

`start` and `finish` accept `"City, ST"` or `"lat,lng"`, e.g. `"41.8781,-87.6298"`.

### Postman

*Import* → *Link* → `http://localhost:8000/api/schema/`. This creates a
collection with every endpoint from the OpenAPI schema.

### The map

Every API response includes a `map_url`. Open it to see the route and the
numbered fuel stops. Click a stop in the list to zoom to it.

## Admin panel

http://localhost:8000/admin/: log in as `admin` / `change-me` (set in `.env`).

- **Fuel stations:** all 6,620 stations, searchable by name, city or ID, and
  filterable by state and price range.
- Stations are **read-only**: they're rebuilt from `data/fuel_prices.csv` on every
  start, so edits would be lost. To change prices, edit the CSV and restart.
- The admin user is created on start from `DJANGO_SUPERUSER_USERNAME` /
  `DJANGO_SUPERUSER_PASSWORD` if it doesn't already exist. Use your own password
  anywhere other than your machine.

## Without Docker

**Requires:** Python 3.13.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

python manage.py migrate
python manage.py load_stations        # ~1s; add -v 2 to list unmatched cities
python manage.py ensure_superuser     # admin user from .env
python manage.py runserver
```

Then open the same URLs as above.

## Tests

```bash
python manage.py test
```

103 tests, about 3 seconds. The routing API is faked, so no network is needed.
CI runs them plus a Docker smoke test on every push.

## Rebuilding the place index (optional)

`data/us_places.csv.gz` is committed, so this is only needed to refresh it. It
downloads about 80 MB of Census and GeoNames data:

```bash
python manage.py build_places
```

## Configuration

All settings come from `.env` or the environment; see `.env.example` and the
table in the [README](README.md#configuration). The ones you're most likely to change:

| Variable | Default |
|---|---|
| `VEHICLE_MAX_RANGE_MILES` | `500` |
| `VEHICLE_MPG` | `10` |
| `STATION_SEARCH_RADIUS_MILES` | `10` |
| `OSRM_BASE_URL` | `https://router.project-osrm.org` |
| `DJANGO_SUPERUSER_USERNAME` / `_PASSWORD` | `admin` / `change-me` |

Restart after changing them: `docker compose up --build`.

## Troubleshooting

| Problem | Fix |
|---|---|
| `Cannot connect to the Docker daemon` | Start Docker Desktop and wait for "Engine running". |
| `docker` commands hang | Docker Desktop's VM is stuck: quit Docker Desktop fully and reopen it. |
| `port is already allocated` | Something else uses port 8000: stop it, or change `"8000:8000"` to e.g. `"8080:8000"` in `docker-compose.yml`. |
| `/api/health/` shows `"stations_loaded": 0` | Station loading failed: check `docker compose logs web`. Without Docker, run `python manage.py load_stations`. |
| API returns 503 `routing_unavailable` | The public OSRM server is down or slow. Retry, or point `OSRM_BASE_URL` at another OSRM server. |
| Map shows "Access blocked" tiles | Hard-refresh the page (Cmd/Ctrl + Shift + R) to drop cached blocked tiles. |
| Admin login fails | The user is created only if missing. Check `DJANGO_SUPERUSER_*` in `.env`, or run `python manage.py changepassword admin`. |
| Admin looks unstyled | Rebuild the image (`docker compose up --build`); static files are collected during the build. |
