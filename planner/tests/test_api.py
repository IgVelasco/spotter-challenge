import json
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

import pytest

from planner import services
from planner.fuel import InfeasibleRoute
from planner.models import Station
from planner.routing import RouteNotFound, RoutingUnavailable
from planner.views import PlanningThrottle

URL = "/api/v1/route-plan/"
MAP_URL = "/api/v1/route-plan/map/"


def post(client, body):
    return client.post(URL, body, content_type="application/json")


def assert_error(response, status, code):
    assert response.status_code == status
    body = response.json()
    assert body["error"]["code"] == code
    assert body["error"]["message"]
    return body["error"]


@pytest.fixture
def failing_planner(monkeypatch):
    def use(error):
        def fail(*args, **kwargs):
            raise error

        monkeypatch.setattr(services, "plan_trip", fail)

    return use


def test_long_trip_returns_route_stops_and_cost(client, ors_replay, real_stations):
    ors_replay("ors_chicago_denver.json.gz")

    response = post(client, {"start": "Chicago, IL", "finish": "Denver, CO"})

    assert response.status_code == 200
    body = response.json()
    assert body["route"]["distance_miles"] == pytest.approx(1000.7, abs=0.1)
    assert body["route"]["geometry"]["type"] == "LineString"
    assert len(body["route"]["geometry"]["coordinates"]) > 100
    assert len(body["fuel_stops"]) >= 2
    stop = body["fuel_stops"][0]
    assert set(stop) == {
        "opis_id",
        "name",
        "address",
        "city",
        "state",
        "latitude",
        "longitude",
        "route_mile",
        "miles_off_route",
        "price_per_gallon",
        "gallons",
        "cost_usd",
    }
    summary = body["fuel_summary"]
    assert Decimal(summary["total_fuel_cost_usd"]) == sum(
        Decimal(s["cost_usd"]) for s in body["fuel_stops"]
    )
    assert summary["starting_fuel_cost_usd"] is None
    assert body["routing_api_calls"] == 1
    assert body["assumptions"]["vehicle_range_miles"] == 500
    assert body["assumptions"]["miles_per_gallon"] == 10
    assert "OpenStreetMap" in body["attribution"]


def test_money_is_returned_as_strings_with_two_decimals(client, ors_replay, real_stations):
    ors_replay("ors_chicago_denver.json.gz")

    body = post(client, {"start": "Chicago, IL", "finish": "Denver, CO"}).json()

    for value in [s["cost_usd"] for s in body["fuel_stops"]] + [
        body["fuel_summary"]["total_fuel_cost_usd"]
    ]:
        assert isinstance(value, str)
        assert len(value.split(".")[1]) == 2


def test_starting_fuel_price_adds_the_burned_start_tank_to_the_total(
    client, ors_replay, real_stations
):
    ors_replay("ors_chicago_milwaukee.json")

    body = post(
        client,
        {"start": "Chicago, IL", "finish": "Milwaukee, WI", "starting_fuel_price_usd": "3.50"},
    ).json()

    summary = body["fuel_summary"]
    assert body["fuel_stops"] == []
    assert summary["fuel_purchased_cost_usd"] == "0.00"
    assert summary["starting_fuel_cost_usd"] == "32.24"
    assert summary["total_fuel_cost_usd"] == "32.24"


@pytest.mark.parametrize(
    "start",
    [
        "41.837045,-87.684939",
        {"latitude": 41.837045, "longitude": -87.684939},
    ],
)
def test_accepts_coordinates(client, ors_replay, real_stations, start):
    ors_replay("ors_chicago_milwaukee.json")

    response = post(client, {"start": start, "finish": "Milwaukee, WI"})

    assert response.status_code == 200
    assert response.json()["start"]["latitude"] == pytest.approx(41.837045)


def test_map_url_reproduces_the_same_trip(client, ors_replay, real_stations):
    ors_replay("ors_chicago_milwaukee.json")

    body = post(
        client,
        {"start": "Chicago, IL", "finish": "Milwaukee, WI", "starting_fuel_price_usd": "3.5"},
    ).json()

    query = parse_qs(urlparse(body["map_url"]).query)
    assert urlparse(body["map_url"]).path == MAP_URL
    assert query["start"] == ["41.837045,-87.684939"]
    assert query["starting_fuel_price_usd"] == ["3.5"]


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"finish": "Denver, CO"}, "start"),
        ({"start": "Chicago, IL", "finish": "Atlantis, CO"}, "finish"),
        ({"start": "Paris, FR", "finish": "Denver, CO"}, "start"),
        ({"start": "48.86,2.35", "finish": "Denver, CO"}, "start"),
        (
            {"start": "Chicago, IL", "finish": "Denver, CO", "starting_fuel_price_usd": "-1"},
            "starting_fuel_price_usd",
        ),
        ({"start": "Chicago, IL", "finish": "Denver, CO", "via": "Omaha, NE"}, "via"),
    ],
)
def test_invalid_requests_return_field_errors(client, body, field):
    error = assert_error(post(client, body), 400, "invalid_request")

    assert field in error["details"]


def test_malformed_json_is_rejected(client):
    response = client.post(URL, "{not json", content_type="application/json")

    assert_error(response, 400, "parse_error")


def test_non_json_body_is_rejected(client):
    response = client.post(URL, "start=Chicago", content_type="application/x-www-form-urlencoded")

    assert_error(response, 415, "unsupported_media_type")


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (RouteNotFound("Could not find routable point"), 422, "route_not_found"),
        (InfeasibleRoute("Cannot reach the station at mile 900"), 422, "no_feasible_fuel_plan"),
        (RoutingUnavailable("The routing provider timed out"), 502, "routing_unavailable"),
    ],
)
def test_planning_failures_map_to_json_errors(client, failing_planner, error, status, code):
    failing_planner(error)

    response = post(client, {"start": "Chicago, IL", "finish": "Denver, CO"})

    assert assert_error(response, status, code)["message"] == str(error)


def test_wrong_method_returns_json_error(client):
    assert_error(client.get(URL), 405, "method_not_allowed")


def test_unknown_api_path_returns_json_error(client):
    assert_error(client.get("/api/v1/nope/"), 404, "not_found")


def test_requests_are_rate_limited(client, monkeypatch, failing_planner):
    failing_planner(RouteNotFound("no route"))
    monkeypatch.setitem(PlanningThrottle.THROTTLE_RATES, PlanningThrottle.scope, "1/minute")

    post(client, {"start": "Chicago, IL", "finish": "Denver, CO"})
    response = post(client, {"start": "Chicago, IL", "finish": "Denver, CO"})

    assert_error(response, 429, "throttled")


def test_map_page_renders_trip_data(client, ors_replay, real_stations):
    ors_replay("ors_chicago_denver.json.gz")

    response = client.get(MAP_URL, {"start": "Chicago, IL", "finish": "Denver, CO"})

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/html")
    content = response.content.decode()
    assert 'id="trip-data"' in content
    assert "leaflet@1.9.4" in content


def test_map_page_escapes_station_names(client, ors_replay, real_stations):
    ors_replay("ors_chicago_denver.json.gz")
    Station.objects.update(name="<script>alert(1)</script>")

    content = client.get(MAP_URL, {"start": "Chicago, IL", "finish": "Denver, CO"}).content

    assert b"<script>alert(1)</script>" not in content


def test_map_page_shows_errors(client):
    response = client.get(MAP_URL, {"start": "Atlantis, CO", "finish": "Denver, CO"})

    assert response.status_code == 400
    assert b"Atlantis" in response.content


def test_response_echoes_what_the_caller_sent(client, ors_replay, real_stations):
    ors_replay("ors_chicago_milwaukee.json")
    finish = {"latitude": 43.0389, "longitude": -87.9065}

    body = post(client, {"start": "Chicago, IL", "finish": finish}).json()

    assert body["start"] == {"query": "Chicago, IL", "latitude": 41.837045, "longitude": -87.684939}
    assert body["finish"]["query"] == finish


def test_overlong_location_text_is_rejected_before_lookup(client):
    error = assert_error(
        post(client, {"start": "A" * 300 + ", IL", "finish": "Denver, CO"}), 400, "invalid_request"
    )

    assert "255" in error["details"]["start"][0]


def test_failed_plans_are_logged_with_their_error_code(client, failing_planner, caplog):
    failing_planner(RoutingUnavailable("The routing provider timed out"))
    caplog.set_level("INFO", logger="planner")

    post(client, {"start": "Chicago, IL", "finish": "Denver, CO"})

    [record] = [r for r in caplog.records if r.name == "planner.errors"]
    assert record.levelname == "WARNING"
    assert json.loads(record.getMessage()) == {
        "event": "request_failed",
        "status": 502,
        "code": "routing_unavailable",
        "detail": "The routing provider timed out",
    }


def test_client_error_logs_omit_the_message_because_it_contains_user_input(client, caplog):
    caplog.set_level("INFO", logger="planner")

    post(client, {"start": "Atlantis, NV", "finish": "Denver, CO"})

    [record] = [r for r in caplog.records if r.name == "planner.errors"]
    assert json.loads(record.getMessage()) == {
        "event": "request_failed",
        "status": 400,
        "code": "invalid_request",
    }


def test_map_page_failures_are_logged_like_api_failures(client, failing_planner, caplog):
    failing_planner(RoutingUnavailable("The routing provider returned HTTP 503"))
    caplog.set_level("INFO", logger="planner")

    response = client.get(MAP_URL, {"start": "Chicago, IL", "finish": "Denver, CO"})

    assert response.status_code == 502
    [record] = [r for r in caplog.records if r.name == "planner.errors"]
    assert json.loads(record.getMessage()) == {
        "event": "request_failed",
        "status": 502,
        "code": "routing_unavailable",
        "detail": "The routing provider returned HTTP 503",
    }


def test_map_page_lets_the_browser_send_its_origin_to_the_tile_server(client):
    # OpenStreetMap's tile policy blocks pages whose Referrer-Policy strips the Referer;
    # Django's default "same-origin" does. Sending only the origin keeps the trip's
    # query string private.
    response = client.get(MAP_URL, {"start": "Atlantis, CO", "finish": "Denver, CO"})

    assert response["Referrer-Policy"] == "strict-origin-when-cross-origin"
