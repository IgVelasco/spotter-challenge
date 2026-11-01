# Follow-ups: things to review or improve later

Decisions taken to ship within the time box, with what a better solution would
look like. Each item says why it was deferred and roughly what it would cost.

## Data and station locations

1. **Stations sit at their town's centre, not at the real exit.**
   The CSV has highway descriptors ("I-44, EXIT 283 & US-69") instead of street
   addresses, so street geocoders (Census, Nominatim) can't place them. A station
   can be a few miles from its real location.
   *Better:* match "I-xx, EXIT nnn" against OpenStreetMap `highway=motorway_junction`
   nodes (`ref` = exit number) near the town. Would give exit-level accuracy to
   ~3,500 stations. About 2 hours, plus one offline Overpass download (ODbL attribution).

2. **191 US stations are excluded** because their town is an unincorporated place
   with no Census Gazetteer point (Breezewood PA, Ruther Glen VA, Hope Hull AL…).
   *Better:* add the USGS GNIS "populated places" file as a third lookup source; it
   lists unincorporated communities. Small change in `planner/geodata.py`.

3. **Price rule: highest observed price per station.** 487 stations have several
   prices (median spread $0.10, max $0.90) and the file has no dates, so we can't
   tell which is current. Max makes the reported cost an upper bound.
   *Review:* ask Spotter what repeated rows mean (fuel grade? rack? time?).

4. **One garbled name** (CSV line 6526, a double-encoded "Stuckey's"). Imported
   as-is. *Fix:* repair the encoding in the import, or correct the source row.

5. **Ambiguous town names** resolve by rule (incorporated over CDP, then larger
   area), e.g. "Superior, WI" has a city and a village 3 miles apart. Fine in
   practice; the rule could pick wrongly for far-apart namesakes.

6. **`scripts/build_us_places.py` has no tests of its own.** The row
   classification it uses is tested; the script is a one-off build step whose output
   (`data/us_places.csv`, Census Gazetteer 2025) is committed.

## Routing and fuel model

7. **Coverage is uneven: California has only 16 rows.** On Los Angeles → New York
   the first station along the route is at mile 270. No AK, HI or DC stations at
   all. The API can only plan with the stations it has; it can't invent coverage.

8. **Trip starts with a full tank** (500 miles). The cost is the fuel bought along
   the route, so a trip under 500 miles costs $0. An empty-tank start was tried and
   dropped: with only 16 California rows, trips from LA had no station near the
   origin. Planned: optional `starting_fuel_price_usd` to also cost the starting
   fuel actually burned. *Review:* whether Spotter expects a different convention.

9. **A fixed $10 cost per stop is part of the optimisation.** Pure cheapest-fuel
   plans made 15–18 stops coast to coast, many under 2 gallons; with $10/stop they
   make 7 stops for ~1% more fuel spend. $10 is a judgement call (time off the
   highway), not data. *Review:* expose it as an optional request field if callers
   want to trade stops for price.

10. **Purchases are in 0.1-gallon steps.** The planner works in whole miles of
    range (station miles rounded, destination rounded up), so a purchase can be up
    to ~0.1 gal more than the exact need. Negligible, and never short.

11. **Detours to stations are not routed.** Stations within a corridor of the route
   are projected onto it; the drive off the highway and back isn't in the distance
   or cost. A safety margin on the 500-mile range covers it for feasibility.
   *Better:* a second ORS call through the chosen stations as waypoints, then re-plan
   on the real leg distances (the email allows 2–3 calls). Costs ~1–2 s per request.

12. **Car routing profile.** ORS `driving-car` is used. ORS also has `driving-hgv`
   (heavy goods vehicles), more realistic for trucks. *Check:* its free-plan limits
   and whether routes differ meaningfully.

13. **Lat/lon inputs are checked against US bounding boxes**, not real borders. A
   point in Canada just north of the border box could pass. *Better:* a US polygon
   check (e.g. Natural Earth) if precise validation matters.

## Operations

14. **No retry on a failed routing call.** One ORS request failed transiently during
   testing (cause unknown; failures weren't logged with a reason yet, now they are).
   *Better:* one retry on timeouts and 5xx, within the email's 2–3 call budget.


15. **Corridor matching takes ~0.3 s** on a 2,800-mile route (pure Python, 1-mile
   samples × grid cells). Fine next to the ~2 s ORS call. *Better:* vectorise with
   NumPy or simplify the route geometry first if latency matters.

16. **`routing_api_calls` counts the call a plan needs, not calls actually made.** A
    repeated trip is served from the route cache (~0.3 s instead of ~2–3 s) but still
    reports 1. *Fix:* have `fetch_route` report cache hits.

17. **ORS free quota is 2,000 requests/day** (`api.heigit.org`). Routes are cached by
    endpoints and planning is throttled to 30 requests/minute per client IP, but the
    cache and throttle are per process (Django's local-memory cache). *Better:* a
    shared cache (Redis) if it runs with several workers or servers.

## Deliberately cut from the original design docs

PostgreSQL, dataset versioning/activation, manual station access review, Census
batch geocoding (doesn't fit highway-style addresses), OpenAPI generation, a second
validation routing call, structured JSON logs. Revisit only if a reviewer asks.
