# How this was built

The work started from a short design document and was built in small vertical slices.
Each slice was written test-first, then reviewed before the next one started.
Below are the design (a condensed SDD), then each phase with what it delivered, how it
was checked, and what the review changed.

I built it with Claude Code (Anthropic's AI coding assistant) as a pair programmer. I
set the scope, made the product decisions and reviewed every slice; the assistant did
the data analysis and wrote the code test-first against the real dataset and real
routes. The rules it worked under are in [`CLAUDE.md`](../CLAUDE.md).

## 1. Design (condensed SDD)

### Problem

Given a start and a finish in the USA, return the route, where to buy fuel and the total
fuel cost, for a vehicle with a 500-mile range at 10 mpg, using the supplied price list.
Respond fast and call the routing API as little as possible (one call ideal).

### Constraints that shaped the design

| Constraint | Consequence |
|---|---|
| The price list has no coordinates, and its addresses are highway descriptors ("I-44, EXIT 283 & US-69") | Street geocoders can't place them. Stations are placed offline at their town's centre (Census Gazetteer) |
| One routing call per request | No geocoding API at request time either: start/finish resolve offline from the same Census data. Routes are cached |
| Respond fast | All station data is prepared once at import; a request does one HTTP call plus in-memory work |
| Free routing tier | openrouteservice on `api.heigit.org` (2,000 requests/day). Planning is throttled per client |
| About one day of work | The original design was trimmed (see "Cut from the design" below) |

### Architecture

```
POST /api/v1/route-plan/
  -> validate input             serializers.py
  -> resolve start/finish       locations.py, geodata.py   (offline, Census places)
  -> fetch route                routing.py                 (1 ORS call, cached 24 h)
  -> stations near the route    corridor.py                (10-mile corridor, route miles)
  -> choose stops               fuel.py                    (pure, no I/O)
  -> JSON or HTML map           serializers.py, map.html
errors -> one JSON envelope     errors.py
```

`fuel.py` is pure Python with no database, HTTP or geometry imports, so the
optimisation can be tested exhaustively on its own.

### Key decisions

| Decision | Alternatives considered | Why |
|---|---|---|
| Station at its town's centre | Census address geocoding; Nominatim; OSM exit nodes; All The Places brand data | Address geocoders can't read highway descriptors. Exit and brand matching were prototyped on a branch (below) and not merged |
| Start with a full tank | Start empty | With 16 California rows, the first station from Los Angeles is at mile 270; an empty start can't leave |
| Minimise fuel cost + $10 per stop (dynamic program) | Greedy "cheapest next station" | Greedy made 15–18 stops coast to coast, many under 2 gallons; the DP makes 7 for ~1% more fuel spend |
| Plan with a 480-mile range | Use the full 500 | Leaves room for a 10-mile detour to a station and back |
| Highest listed price per station | Lowest, mean, latest | The file has no dates; the highest price makes the cost an upper bound |
| SQLite | PostgreSQL | 6,435 read-only rows, read in one query per plan; no spatial queries needed |

### Cut from the design

PostgreSQL, dataset versioning and activation, manual station review, Census batch
geocoding, and a second routing call to validate detours. Each is noted in
[`follow-ups.md`](follow-ups.md) where it still matters.

## 2. Phases

Every phase ended with the full test suite, `ruff check`, `ruff format --check` and a
missing-migrations check passing, followed by a review of the slice against the design.

### Phase 0: Scope and data review

**Delivered:** the plan above; a review of the supplied CSV and of similar public
solutions (for ideas, not code).

**Checks:** the CSV was scanned as untrusted input: encoding, formula-injection
prefixes, control characters, malformed rows, duplicates.

**Review findings:**
- No injection payloads, but 620 Canadian rows, 487 stations listed several times with
  different prices, and one double-encoded name.
- Addresses are highway descriptors, so the original "geocode each address" plan
  couldn't work. This moved station location to Census town centres.
- The first design was too large for the time box and was cut down.

### Phase 1: Scaffold
`dfe6209`

**Delivered:** Django 6.1 + DRF project, env-driven settings, non-root Docker image,
Compose file, GitHub Actions CI.

**Review findings:** every dependency version was checked against PyPI rather than
written from memory; one recalled version was wrong and was corrected.

### Phase 2: Station data
`18a3aad`, `1df8983`

**Delivered:** `import_stations` command (header validation, malformed rows reported
with their line number, atomic replace) and offline place lookup built from the Census
2025 Gazetteer (places plus townships).

**Result:** 6,435 of 6,626 US stations located; 191 in unincorporated communities with
no Census point are skipped and listed by the import.

**Review findings:** repeated stations are merged by highest price (documented as an
assumption); ambiguous town names resolve by a fixed, tested rule.

### Phase 3: Fuel planner
`c8dc740`, `797d81f`, `81d25ff`

**Delivered:** the pure fuel optimiser.

**Checks:**
- Hand-worked plans.
- A brute-force oracle compared on 400 random small routes.
- Mutation checks: deliberately broken copies of the planner must fail the tests.

**Review findings:**
- *Empty starting tank failed* on Los Angeles routes (first station at mile 270), so
  the model was changed to a full tank, with optional `starting_fuel_price_usd` to cost
  the starting fuel burned.
- *Greedy plans were impractical* (15–18 stops), so the planner was replaced by a
  dynamic program with a $10 stop cost.
- *The first mutation run proved nothing:* the mutations hadn't been applied, so the
  tests passed against the unchanged code. They were redone with exact replacements and
  each mutation was confirmed to fail.
- One hand-worked expectation was wrong (49.5 gallons; correct is 49.0) and was fixed.

### Phase 4: Routing and corridor
`147fcfa`

**Delivered:**
- An openrouteservice client: one call, 15 s timeout, 24 h cache keyed by endpoints.
- `"City, ST"` / `"lat,lon"` input resolution.
- Corridor matching: the route is resampled every mile and stations are bucketed in a
  lat/lon grid.

**Checks:** real ORS responses (Chicago → Milwaukee, Chicago → Denver) were recorded
once and replayed in tests; only the HTTP transport is replaced, and the planner,
corridor and database code run for real.

**Review findings:** the provider's old host allows 200 requests/day, so the client
moved to `api.heigit.org` (2,000/day).

### Phase 5: API, map and docs
`937674d`, `c55fec7`, `f80eb8d`

**Delivered:**
- `POST /api/v1/route-plan/`, with one JSON error envelope for every failure and
  per-client throttling.
- The HTML map, with all route data escaped through `json_script`.
- README and Postman collection.

**Review findings:** `.env.example` shipped with `DEBUG=1`, which made 404s return
Django's HTML page instead of the JSON error. It was set to off, with a test.

### Phase 6: Gap review against the design
`0c984dd`, `9989c6c`

The finished slices were re-read against the SDD and against strong public solutions
to find gaps.

**Delivered:**
- Responses echo the original inputs.
- Location text is capped at 255 characters.
- Trips that fit in one tank skip station matching.
- The health check reports database and station state.
- One structured log line per plan: counts and timings only, never places or
  coordinates.

**Review findings:** the first 255-character test passed for the wrong reason (a
different validation rejected the input). It was rewritten to assert the specific
error message.

### Phase 7: Manual testing and map clarity
`3766e0c`, `87e2a3d`

**Delivered:** each fuel stop has a highlighted, animated 10-mile stretch of route
around its town centre: "look for it between mile X and Y". The JSON returns the same
stretch as `route_stretch`.

**Review findings:**
- *Map tiles returned 403.* The fix was the `Referrer-Policy` header that the
  OpenStreetMap tile policy requires.
- *A transient routing 502 left no reason in the logs.* Failures are now logged, with
  the provider error for 5xx responses.
- *Pins can sit a few miles off the route* (town centre, not the exit). Exit-level
  locations were prototyped on a separate branch. All The Places brand data matched
  32–39% of stations; OSM exit nodes were estimated to reach ~66%. That wasn't worth
  the extra data and licence weight for this exercise, so it wasn't merged. The
  highlighted stretch solves the driver's actual question instead.

### Phase 8: Load and performance
`59cf7e5`

**Checks:** load tests with gunicorn, with the throttle raised for the test.

**Review findings:** profiling a coast-to-coast trip showed ~25% of CPU went to cutting
each stop's stretch, because the route was measured again for every stop. The route is
now measured once. With repeated LA → New York trips (routes served from the cache),
throughput went from 4.0 to 5.1 requests/s on 2 workers and from 7.8 to 9.3 on
4 workers. Short trips serve ~500 requests/s (2 workers) to ~1,000 (4 workers).

**Remaining limits, in order:**
1. The routing provider's quota and rate.
2. Corridor matching CPU on long routes.
3. The cache and throttle being per process.

See [`follow-ups.md`](follow-ups.md).

### Phase 9: OpenAPI and Swagger UI
`37f3b32`, `f790d9f`

**Delivered:** an OpenAPI 3 schema with request and response examples and every error
response, served by Swagger UI at `/api/v1/docs/`.

**Checks:** drf-spectacular officially lists Django up to 6.0. It was verified on this
exact stack (Django 6.1.2, DRF 3.18.3) and the schema is generated with
`--validate --fail-on-warn` inside the test suite, so an incompatible upgrade fails CI.

**Review findings:**
- Bundled Swagger assets aren't served with `DEBUG` off, so they load from a CDN.
- The CDN's default `@latest` URL was pinned to 5.34.1, with a test, so the docs can't
  change underneath the project.
