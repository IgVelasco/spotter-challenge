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

8. **Trip starts with an empty tank** and the first purchase is at a station near
   the origin (decided with Nacho). The short drive from the origin to that station
   is not charged. *Review:* make starting fuel a request option if Spotter expects
   a full tank.

9. **Detours to stations are not routed.** Stations within a corridor of the route
   are projected onto it; the drive off the highway and back isn't in the distance
   or cost. A safety margin on the 500-mile range covers it for feasibility.
   *Better:* a second ORS call through the chosen stations as waypoints, then re-plan
   on the real leg distances (the email allows 2–3 calls). Costs ~1–2 s per request.

10. **Car routing profile.** ORS `driving-car` is used. ORS also has `driving-hgv`
   (heavy goods vehicles), more realistic for trucks. *Check:* its free-plan limits
   and whether routes differ meaningfully.

11. **Lat/lon inputs are checked against US bounding boxes**, not real borders. A
   point in Canada just north of the border box could pass. *Better:* a US polygon
   check (e.g. Natural Earth) if precise validation matters.

## Operations

12. **Corridor matching takes ~0.3 s** on a 2,800-mile route (pure Python, 1-mile
   samples × grid cells). Fine next to the ~2 s ORS call. *Better:* vectorise with
   NumPy or simplify the route geometry first if latency matters.

13. **Stations are cached in memory per process.** Re-running `import_stations`
   while the server runs needs a restart to be seen (Docker always imports before
   starting the server).

14. **ORS free quota is 2,000 requests/day** (`api.heigit.org`). Routes are cached by
   endpoints, but there's no app-level rate limit to protect the key.

## Deliberately cut from the original design docs

PostgreSQL, dataset versioning/activation, manual station access review, Census
batch geocoding (doesn't fit highway-style addresses), OpenAPI generation, a second
validation routing call, structured JSON logs. Revisit only if a reviewer asks.
