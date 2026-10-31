import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from planner.corridor import haversine_miles, stations_along_route
from planner.geodata import Point

MILES_PER_DEGREE_LATITUDE = 69.09
FIXTURE = Path(__file__).parent / "fixtures" / "ors_chicago_milwaukee.json"


@dataclass(frozen=True)
class FakeStation:
    name: str
    latitude: float
    longitude: float


def north_of(latitude, miles):
    return latitude + miles / MILES_PER_DEGREE_LATITUDE


# Two vertices only: a straight east-west road along latitude 40, about 106 miles long.
STRAIGHT_ROUTE = [[-100.0, 40.0], [-98.0, 40.0]]
STRAIGHT_MILES = haversine_miles(Point(40.0, -100.0), Point(40.0, -98.0))


def test_haversine_matches_known_distance():
    chicago, milwaukee = Point(41.8781, -87.6298), Point(43.0389, -87.9065)

    assert haversine_miles(chicago, milwaukee) == pytest.approx(81.2, abs=0.5)


def test_station_beside_a_long_segment_is_found_with_its_mile():
    station = FakeStation("middle", north_of(40.0, 3), -99.0)

    [found] = stations_along_route(STRAIGHT_ROUTE, STRAIGHT_MILES, [station], max_offset_miles=5)

    assert found.station == station
    assert found.mile == pytest.approx(STRAIGHT_MILES / 2, abs=1)
    assert found.offset_miles == pytest.approx(3, abs=0.2)


def test_station_beyond_the_corridor_is_excluded():
    station = FakeStation("far", north_of(40.0, 20), -99.0)

    assert stations_along_route(STRAIGHT_ROUTE, STRAIGHT_MILES, [station], 5) == []


def test_results_are_ordered_by_mile():
    stations = [
        FakeStation("east", 40.0, -98.2),
        FakeStation("west", 40.0, -99.8),
        FakeStation("middle", 40.0, -99.0),
    ]

    found = stations_along_route(STRAIGHT_ROUTE, STRAIGHT_MILES, stations, 5)

    assert [f.station.name for f in found] == ["west", "middle", "east"]


def test_miles_are_scaled_to_the_provider_route_distance():
    station = FakeStation("middle", 40.0, -99.0)

    [found] = stations_along_route(STRAIGHT_ROUTE, STRAIGHT_MILES * 1.1, [station], 5)

    assert found.mile == pytest.approx(STRAIGHT_MILES * 1.1 / 2, abs=1)


def test_station_near_two_parts_of_a_route_uses_its_closest_point():
    # Out east along latitude 40, then back west along latitude 40.5.
    route = [[-100.0, 40.0], [-98.0, 40.0], [-98.0, 40.5], [-100.0, 40.5]]
    total = sum(
        haversine_miles(Point(a[1], a[0]), Point(b[1], b[0]))
        for a, b in zip(route, route[1:], strict=False)
    )
    station = FakeStation("near return leg", 40.45, -99.0)

    [found] = stations_along_route(route, total, [station], 5)

    assert found.mile > total / 2
    assert found.offset_miles == pytest.approx(0.05 * MILES_PER_DEGREE_LATITUDE, abs=0.3)


def test_real_route_finds_station_in_a_town_on_the_way():
    body = json.loads(FIXTURE.read_text())
    coordinates = body["features"][0]["geometry"]["coordinates"]
    kenosha = FakeStation("Kenosha", 42.587526, -87.879996)  # Census point, east of I-94
    madison = FakeStation("Madison", 43.087815, -89.429856)  # far west of the route

    found = stations_along_route(coordinates, 92.12, [kenosha, madison], 10)

    assert [f.station.name for f in found] == ["Kenosha"]
    assert 30 < found[0].mile < 70
