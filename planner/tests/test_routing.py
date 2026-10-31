import json
from pathlib import Path

import httpx
import pytest

from planner.geodata import Point
from planner.routing import RouteNotFound, RoutingUnavailable, fetch_route

FIXTURE = Path(__file__).parent / "fixtures" / "ors_chicago_milwaukee.json"
CHICAGO = Point(41.8781, -87.6298)
MILWAUKEE = Point(43.0389, -87.9065)


@pytest.fixture(autouse=True)
def ors_key(settings):
    settings.ORS_API_KEY = "test-key"


def transport_returning(status, body, seen=None):
    def handler(request):
        if seen is not None:
            seen.append(request)
        content = body if isinstance(body, str) else json.dumps(body)
        return httpx.Response(status, text=content)

    return httpx.MockTransport(handler)


def test_parses_real_ors_response():
    route = fetch_route(CHICAGO, MILWAUKEE, transport=transport_returning(200, FIXTURE.read_text()))

    assert route.distance_miles == pytest.approx(92.12, abs=0.01)
    assert route.duration_seconds == pytest.approx(6904.7)
    assert len(route.coordinates) == 918
    assert route.coordinates[0] == pytest.approx([-87.629799, 41.878101], abs=1e-3)
    assert "OpenStreetMap" in route.attribution


def test_sends_key_and_longitude_first_coordinates():
    seen = []
    fetch_route(CHICAGO, MILWAUKEE, transport=transport_returning(200, FIXTURE.read_text(), seen))

    request = seen[0]
    assert request.headers["Authorization"] == "test-key"
    assert json.loads(request.content)["coordinates"] == [[-87.6298, 41.8781], [-87.9065, 43.0389]]


def test_same_endpoints_are_served_from_cache():
    seen = []
    transport = transport_returning(200, FIXTURE.read_text(), seen)

    first = fetch_route(CHICAGO, MILWAUKEE, transport=transport)
    second = fetch_route(CHICAGO, MILWAUKEE, transport=transport)

    assert len(seen) == 1
    assert second == first


def test_unroutable_point_raises_route_not_found():
    body = {"error": {"code": 2010, "message": "Could not find routable point within a radius"}}

    with pytest.raises(RouteNotFound, match="routable point"):
        fetch_route(CHICAGO, MILWAUKEE, transport=transport_returning(404, body))


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (403, {"error": "Access to this API has been disallowed"}),
        (429, {"error": "Rate limit exceeded"}),
        (500, "upstream exploded"),
        (200, "not json"),
        (200, {"features": []}),
    ],
)
def test_provider_failures_raise_routing_unavailable(status, body):
    with pytest.raises(RoutingUnavailable):
        fetch_route(CHICAGO, MILWAUKEE, transport=transport_returning(status, body))


def test_errors_are_not_cached():
    body = {"error": {"code": 2010, "message": "no route"}}
    with pytest.raises(RouteNotFound):
        fetch_route(CHICAGO, MILWAUKEE, transport=transport_returning(404, body))

    route = fetch_route(CHICAGO, MILWAUKEE, transport=transport_returning(200, FIXTURE.read_text()))

    assert route.distance_miles > 0


def test_timeout_raises_routing_unavailable():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(RoutingUnavailable, match="timed out"):
        fetch_route(CHICAGO, MILWAUKEE, transport=httpx.MockTransport(handler))


def test_missing_api_key_raises_routing_unavailable(settings):
    settings.ORS_API_KEY = ""

    with pytest.raises(RoutingUnavailable, match="ORS_API_KEY"):
        fetch_route(CHICAGO, MILWAUKEE, transport=transport_returning(200, FIXTURE.read_text()))


def test_error_messages_never_contain_the_api_key():
    with pytest.raises(RoutingUnavailable) as error:
        fetch_route(CHICAGO, MILWAUKEE, transport=transport_returning(403, {"error": "denied"}))

    assert "test-key" not in str(error.value)
