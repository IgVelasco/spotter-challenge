# Fuel Route Planner

A Django API that takes a start and finish in the USA and returns the driving
route, where to buy fuel along it, and what the fuel costs, for a vehicle with a
500-mile range at 10 miles per gallon, using the supplied fuel price list.

- **One routing call per trip** (openrouteservice); repeated trips are cached.
- **~2–3 s** for a coast-to-coast trip, almost all of it the routing provider;
  local planning takes ~0.3 s. Cached repeats return in ~0.3 s. Trips that fit in
  one tank skip station matching entirely.
- **Fewer, sensible stops:** the planner minimises fuel cost plus a small fixed cost
  per stop. LA → New York takes 7 stops instead of 15 tiny top-ups.

## Quick start (Docker)

```bash
cp .env.example .env
# Set ORS_API_KEY in .env (free key from https://account.heigit.org)
# and DJANGO_SECRET_KEY to any long random string.
docker compose up --build
```

The container runs migrations, imports the stations, then serves on
<http://localhost:8000>. Check it with:

```bash
curl -X POST http://localhost:8000/api/v1/route-plan/ \
  -H 'Content-Type: application/json' \
  -d '{"start": "Chicago, IL", "finish": "Denver, CO"}'
```

Or open the map: <http://localhost:8000/api/v1/route-plan/map/?start=Chicago,%20IL&finish=Denver,%20CO>

A Postman collection is in [`postman/fuel-route-planner.postman_collection.json`](postman/fuel-route-planner.postman_collection.json).
Interactive API docs (Swagger UI): <http://localhost:8000/api/v1/docs/>; the OpenAPI 3
schema is at `/api/v1/schema/`.

## Local setup

Requires Python 3.12+ (developed on 3.14).

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env              # then set ORS_API_KEY and DJANGO_SECRET_KEY
python manage.py migrate
python manage.py import_stations  # ~1 s; prints what was imported and skipped
python manage.py runserver
```

## API

### `POST /api/v1/route-plan/`

| Field | Required | Format |
|---|---|---|
| `start` | yes | `"City, ST"`, `"lat,lon"`, or `{"latitude": .., "longitude": ..}` (text up to 255 characters) |
| `finish` | yes | same as `start` |
| `starting_fuel_price_usd` | no | price per gallon paid for the starting tank, e.g. `"3.50"` |

City names are resolved offline from Census data, so they don't use routing
quota. Coordinates must be inside the US. The response echoes each input as `query`
next to the coordinates it resolved to.

Example: Chicago → Denver with `"starting_fuel_price_usd": "3.50"` (real
response, route geometry shortened):

```json
{
  "start": {"query": "Chicago, IL", "latitude": 41.837045, "longitude": -87.684939},
  "finish": {"query": "Denver, CO", "latitude": 39.76185, "longitude": -104.881105},
  "route": {
    "distance_miles": 1000.7,
    "duration_hours": 15.93,
    "geometry": {"type": "LineString", "coordinates": [[-87.684892, 41.837051], "..."]}
  },
  "fuel_stops": [
    {
      "opis_id": 70467, "name": "QUIKTRIP #598", "address": "I-80, EXIT 439, SR-370",
      "city": "Omaha", "state": "NE", "latitude": 41.262705, "longitude": -96.053475,
      "route_mile": 470.5, "miles_off_route": 2.7,
      "price_per_gallon": "2.927", "gallons": 7.8, "cost_usd": "22.83",
      "route_stretch": {"start_mile": 465.5, "end_mile": 475.5,
                        "geometry": {"type": "LineString", "coordinates": ["..."]}}
    },
    {
      "opis_id": 68368, "name": "AKAL TRAVEL CENTER", "address": "I-80 EX 360",
      "city": "Waco", "state": "NE", "latitude": 40.897, "longitude": -97.461747,
      "route_mile": 558.1, "miles_off_route": 5.2,
      "price_per_gallon": "2.799", "gallons": 44.3, "cost_usd": "124.00",
      "route_stretch": {"start_mile": 553.1, "end_mile": 563.1, "geometry": "..."}
    }
  ],
  "fuel_summary": {
    "gallons_used": 100.1,
    "gallons_purchased": 52.1,
    "starting_fuel_gallons_used": 48.0,
    "fuel_purchased_cost_usd": "146.83",
    "starting_fuel_cost_usd": "167.91",
    "total_fuel_cost_usd": "314.74"
  },
  "assumptions": {
    "vehicle_range_miles": 500, "miles_per_gallon": 10, "starting_tank": "full",
    "stop_cost_usd": 10, "max_miles_off_route": 10,
    "station_location": "centre of the station's town",
    "price_rule": "highest listed price per station"
  },
  "routing_api_calls": 1,
  "map_url": "http://localhost:8000/api/v1/route-plan/map/?start=41.837045%2C-87.684939&finish=39.76185%2C-104.881105&starting_fuel_price_usd=3.5",
  "attribution": "openrouteservice.org | OpenStreetMap contributors"
}
```

**Checking the numbers.** 1,000.7 miles at 10 mpg uses 100.07 gallons. The two
stops buy 7.8 gal × $2.927 = $22.83 and 44.3 gal × $2.799 = $124.00, so 52.1 gallons
for $146.83. The remaining 47.97 gallons come from the starting tank, costed at the
optional $3.50: $167.91. Total $314.74. (The planner keeps 2 gallons of the 50 in
reserve for detours to stations, so long trips use at most 48 from the start tank.)

**Where to stop.** A stop's `latitude`/`longitude` is its town's centre (see
[How it works](#how-it-works)), so each stop also has a `route_stretch`: the 10 miles
of route around its `route_mile`, where the road passes that town. The map animates
these stretches in orange as "watch for the station here".

**Total cost.** The vehicle starts with a full tank. `fuel_purchased_cost_usd` is
what is spent at the stops. If `starting_fuel_price_usd` is given, the starting
fuel actually burned is costed too and included in `total_fuel_cost_usd`; without
it, the total is the purchases only (so a trip under ~480 miles costs $0 and
`gallons_used` still shows the consumption). Money is returned as strings with two
decimals.

### `GET /api/v1/route-plan/map/?start=..&finish=..[&starting_fuel_price_usd=..]`

The same plan drawn on a Leaflet map with the stops and totals; each stop's
`route_stretch` is highlighted with an animated orange line (static if the browser
asks for reduced motion). Every JSON
response includes its `map_url`.

### Errors

All errors share one shape:

```json
{"error": {"code": "invalid_request", "message": "The request is invalid",
           "details": {"start": ["Unknown US city \"Atlantis, NV\""]}}}
```

| HTTP | `code` | When |
|---|---|---|
| 400 | `invalid_request`, `parse_error` | bad or unknown fields, unknown city, non-US coordinates, malformed JSON |
| 404 / 405 / 415 | `not_found`, `method_not_allowed`, `unsupported_media_type` | wrong path, method or content type |
| 422 | `route_not_found` | no road route between the points |
| 422 | `no_feasible_fuel_plan` | a gap between stations is longer than the vehicle's range |
| 429 | `throttled` | more than 30 plans per minute from one client |
| 502 | `routing_unavailable` | routing provider failed, timed out or rejected the key |

`GET /api/v1/health/` returns `{"status": "ok", "stations": 6435}`, or HTTP 503 with a
reason if the database is unreachable or no stations have been imported.

Each plan logs one JSON line with stage timings and counts (no places or
coordinates), and each failed request logs its status and error code.

## How it works

```
start/finish ──> resolve (offline Census places) ──> ORS route (1 call, cached)
     ──> stations within 10 mi of the route, with their route mile
     ──> fuel planner (cost + $10/stop, 480-mile planning range) ──> JSON / map
```

**Station locations.** The price list has no coordinates, and its addresses are
highway descriptors ("I-44, EXIT 283 & US-69") rather than street addresses, so
street geocoders can't place them. Each station is placed at its town's centre
using the public-domain Census Gazetteer (places plus townships), bundled as
`data/us_places.csv`. This locates 6,435 of the 6,626 US stations; the other 191
are in unincorporated communities with no Census point and are left out (the
import lists them). 620 Canadian rows are skipped. Where a station appears several
times with different prices, the highest price is used, since the file has no
dates to tell which is current.

**Stations along the route.** The route is resampled to a point every mile and
stations are bucketed into a lat/lon grid, so each point only checks nearby
stations. Stations within 10 miles of the route are kept (town centres can be a
few miles from the highway), each with its mile along the route.

**Choosing stops.** The pure cheapest-fuel plan chases every small price drop with
tiny top-ups (15–18 stops coast to coast, some under a gallon). The planner instead
minimises *fuel cost + $10 per stop* with a dynamic program over the fuel in the
tank (`planner/fuel.py`), which takes ~50 ms for hundreds of stations. It plans
with a 480-mile range so a 10-mile detour to a station and back always fits within
the real 500 miles. With the stop cost set to zero it gives the classic optimal
"buy just enough to reach the next cheaper station" plan; the tests check it
against a brute-force search on random routes.

**Routing.** openrouteservice (`driving-car`) via `api.heigit.org`, free tier
2,000 requests/day. Routes are cached for a day per start/finish pair.

## Tests

```bash
pytest          # 169 tests, ~14 s
ruff check . && ruff format --check .
```

- `test_fuel.py`: hand-worked fuel plans, plus a brute-force comparison on 400
  random small routes.
- `test_services.py`, `test_api.py`: the full pipeline on the **real station data**,
  replaying **recorded real ORS responses** (Chicago → Milwaukee, Chicago → Denver),
  including every error path, throttling and HTML escaping on the map.
- `test_live.py`: end to end against the real ORS API; runs when `ORS_API_KEY` is
  set, skipped otherwise (as in CI).
- Import, Census place matching, routing adapter and geometry have their own tests.

CI (GitHub Actions) runs lint, a format check, a missing-migrations check and the
test suite.

## Project layout

```
config/                     Django settings and URLs
planner/
  views.py                  HTTP endpoints (API + map page)
  serializers.py            request validation and response shape
  errors.py                 the single JSON error format
  openapi.py                OpenAPI examples and error responses (Swagger UI)
  services.py               plan_trip: route -> stations -> fuel plan -> totals
  routing.py                openrouteservice client (one call, cached)
  corridor.py               stations near the route and their route mile
  fuel.py                   fuel stop optimiser (pure Python)
  locations.py, geodata.py  "City, ST" and coordinate handling (Census places)
  models.py                 Station
  management/commands/import_stations.py
  templates/planner/map.html
data/                       fuel price CSV (as supplied) and Census places
scripts/build_us_places.py  rebuilds data/us_places.csv from Census Gazetteer files
docs/how-it-was-built.md    design (SDD), build phases and review findings
docs/follow-ups.md          known limitations and what a better solution would be
```

## Limitations

The main ones: stations are at town centres rather than their exact exit, coverage
follows the supplied file (only 16 California rows; none in AK, HI or DC), detours to
stations are not routed, and prices are a static snapshot. See
[`docs/follow-ups.md`](docs/follow-ups.md) for the full list and how each could be
improved.

## How this was built

Designed first, then built in ten reviewed phases. A short design document (SDD)
set the architecture and the key decisions. Each phase was a vertical slice:
written test-first, run against the real station data and recorded real routes,
then reviewed before the next one started.

| Phase | Slice | What the review changed |
|---|---|---|
| 0 | Scope and data review | Highway-style addresses can't be geocoded, so stations sit at town centres; the design was trimmed to a day |
| 1 | Scaffold, Docker, CI | Dependency versions verified against PyPI |
| 2 | Station import | 6,435 of 6,626 US stations located; the 191 left out are listed |
| 3 | Fuel planner | Full starting tank (LA's first station is at mile 270); greedy (15–18 stops) replaced by a cost + $10/stop DP |
| 4 | Routing and corridor | One cached ORS call; moved to the 2,000/day host |
| 5 | API and map | JSON errors even for 404s (DEBUG off by default) |
| 6 | Gap review against the design | Input echo, length caps, health check, structured logs |
| 7 | Manual testing | Map tile fix; failure logging; highlighted stretch where each stop is |
| 8 | Load testing | Route measured once per plan: +19–28% throughput on long trips |
| 9 | OpenAPI / Swagger | Schema validated in CI; Swagger UI pinned |

The design, each phase's checks and every review finding are in
[`docs/how-it-was-built.md`](docs/how-it-was-built.md).

Built with Claude Code (Anthropic's AI coding assistant) as a pair programmer. I
set the scope, made the product decisions and reviewed each slice; the assistant
did the data analysis and wrote the code test-first. Its working rules are in
[`CLAUDE.md`](CLAUDE.md).

## Data and attribution

- Fuel prices: `data/fuel-prices-for-be-assessment.csv`, supplied with the assignment.
- Town coordinates: U.S. Census Bureau 2025 Gazetteer files (public domain).
- Routing: [openrouteservice](https://openrouteservice.org/); map data ©
  [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors; map tiles
  from OpenStreetMap.
