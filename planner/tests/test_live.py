"""End-to-end against the real openrouteservice API and the real station data.

Runs when ORS_API_KEY is configured (e.g. in a local .env); CI has no key, so it skips.
Each run spends one request of the free daily quota.
"""

import pytest
from django.conf import settings

pytestmark = pytest.mark.skipif(not settings.ORS_API_KEY, reason="ORS_API_KEY not configured")


def test_real_trip_through_the_api(client, real_stations):
    response = client.post(
        "/api/v1/route-plan/",
        {"start": "Chicago, IL", "finish": "Denver, CO"},
        content_type="application/json",
    )

    assert response.status_code == 200, response.content
    body = response.json()
    assert 950 < body["route"]["distance_miles"] < 1050
    assert len(body["fuel_stops"]) >= 2
    assert float(body["fuel_summary"]["total_fuel_cost_usd"]) > 0
