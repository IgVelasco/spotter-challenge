# Project guidance for AI assistants

Django 6.1 + DRF API that plans fuel stops along a US driving route. See README.md
for behaviour and docs/follow-ups.md for known limitations.

## Commands

```bash
pip install -r requirements-dev.txt
python manage.py migrate && python manage.py import_stations
pytest                                  # full suite; test_live.py needs ORS_API_KEY
ruff check . && ruff format --check .
python manage.py makemigrations --check --dry-run
```

## Rules for changes

- Test first. Tests use the real station data and recorded real ORS responses;
  only the HTTP transport is replaced. Don't mock planner, corridor or database code.
- One ORS directions call per trip. Never geocode stations or endpoints at request
  time; places resolve offline from data/us_places.csv.
- Every API error goes through planner/errors.py and uses
  {"error": {"code", "message", "details"?}}.
- Vehicle constants live in planner/fuel.py; corridor and planning range in
  planner/services.py. Don't repeat the numbers elsewhere.
- planner/fuel.py stays pure: no ORM, HTTP or geometry imports.
- Logs carry counts and timings only, never places or coordinates.
- Never commit .env or keys; the ORS free quota is 2,000 requests/day.
