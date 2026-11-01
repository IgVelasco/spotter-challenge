import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from planner import corridor
from planner.corridor import (
    RouteMeasure,
    haversine_miles,
    stations_along_route,
    thin_line,
)
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


def test_thin_line_keeps_ends_and_drops_points_closer_than_spacing():
    line = [[-100.0, 40.0], [-100.0, 40.001], [-100.0, 40.002], [-100.0, 40.1], [-100.0, 40.1001]]

    thinned = thin_line(line, spacing_miles=1)

    assert thinned == [[-100.0, 40.0], [-100.0, 40.1], [-100.0, 40.1001]]


def test_thin_line_shrinks_a_real_route():
    coordinates = json.loads(FIXTURE.read_text())["features"][0]["geometry"]["coordinates"]

    thinned = thin_line(coordinates, spacing_miles=0.5)

    assert thinned[0] == coordinates[0]
    assert thinned[-1] == coordinates[-1]
    assert len(thinned) < len(coordinates) / 2


def test_route_stretch_interpolates_its_ends_on_a_straight_road():
    stretch = RouteMeasure(STRAIGHT_ROUTE, STRAIGHT_MILES).stretch(
        STRAIGHT_MILES / 4, STRAIGHT_MILES / 2
    )

    assert stretch == [
        pytest.approx([-99.5, 40.0], abs=1e-3),
        pytest.approx([-99.0, 40.0], abs=1e-3),
    ]


def test_route_stretch_keeps_the_vertices_inside_it():
    route = [[-100.0, 40.0], [-99.0, 40.0], [-98.0, 40.0]]
    total = haversine_miles(Point(40.0, -100.0), Point(40.0, -98.0))

    stretch = RouteMeasure(route, total).stretch(total / 4, total * 3 / 4)

    assert [round(lon, 2) for lon, _ in stretch] == [-99.5, -99.0, -98.5]


def test_route_stretch_is_clipped_to_the_route():
    stretch = RouteMeasure(STRAIGHT_ROUTE, STRAIGHT_MILES).stretch(-5, STRAIGHT_MILES + 5)

    assert stretch == [[-100.0, 40.0], [-98.0, 40.0]]


def test_route_stretch_uses_the_provider_mile_scale():
    # The provider says the road is 10% longer than the drawn line; mile 55 of 110.
    stretch = RouteMeasure(STRAIGHT_ROUTE, STRAIGHT_MILES * 1.1).stretch(
        0, STRAIGHT_MILES * 1.1 / 2
    )

    assert stretch[-1] == pytest.approx([-99.0, 40.0], abs=1e-3)


def test_route_stretch_on_a_real_route_spans_the_requested_miles():
    coordinates = json.loads(FIXTURE.read_text())["features"][0]["geometry"]["coordinates"]

    stretch = RouteMeasure(coordinates, 92.12).stretch(40, 50)

    length = sum(
        haversine_miles(Point(a[1], a[0]), Point(b[1], b[0]))
        for a, b in zip(stretch, stretch[1:], strict=False)
    )
    assert length * 92.12 / sum(
        haversine_miles(Point(a[1], a[0]), Point(b[1], b[0]))
        for a, b in zip(coordinates, coordinates[1:], strict=False)
    ) == pytest.approx(10, abs=0.01)


def test_stretches_reuse_one_measurement_of_the_route(monkeypatch):
    measure = RouteMeasure(STRAIGHT_ROUTE, STRAIGHT_MILES)

    def no_distance_maths(*args):
        raise AssertionError("stretch() must not re-measure the route")

    monkeypatch.setattr(corridor, "haversine_miles", no_distance_maths)

    assert len(measure.stretch(10, 20)) == 2
