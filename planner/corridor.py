"""Find stations close to a route and where along it they are.

The route is resampled to a point every mile, stations are bucketed into a grid of
lat/lon cells, and each sample only measures stations in nearby cells. A station's
mile is that of its closest sample, scaled so the route's end matches the
provider's road distance.
"""

import math
from dataclasses import dataclass
from typing import Any

from planner.geodata import Point

EARTH_RADIUS_MILES = 3958.8
SAMPLE_SPACING_MILES = 1.0
GRID_CELL_DEGREES = 0.25
_MILES_PER_DEGREE_LATITUDE = 69.09


@dataclass(frozen=True)
class CorridorStation:
    station: Any
    mile: float
    offset_miles: float


def haversine_miles(a: Point, b: Point) -> float:
    lat1, lat2 = math.radians(a.latitude), math.radians(b.latitude)
    dlat = lat2 - lat1
    dlon = math.radians(b.longitude - a.longitude)
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(h))


def stations_along_route(coordinates, route_miles, stations, max_offset_miles):
    """Stations within max_offset_miles of the route, ordered by route mile.

    coordinates: GeoJSON [longitude, latitude] pairs from the routing provider.
    stations: objects with latitude and longitude attributes.
    """
    samples, polyline_miles = _resample(coordinates)
    scale = route_miles / polyline_miles if polyline_miles else 1.0
    grid = _grid(stations)

    closest = {}  # station index -> (offset, mile)
    for point, mile in samples:
        for index in _nearby_station_indexes(grid, point, max_offset_miles):
            offset = haversine_miles(point, _point(stations[index]))
            if offset <= max_offset_miles and offset < closest.get(index, (math.inf,))[0]:
                closest[index] = (offset, mile * scale)

    found = [
        CorridorStation(stations[index], mile, offset) for index, (offset, mile) in closest.items()
    ]
    return sorted(found, key=lambda f: f.mile)


def _point(station):
    return Point(station.latitude, station.longitude)


def _resample(coordinates):
    """Points at most SAMPLE_SPACING_MILES apart, each with its distance from the start."""
    vertices = [Point(lat, lon) for lon, lat in coordinates]
    samples, total = [], 0.0
    for start, end in zip(vertices, vertices[1:], strict=False):
        length = haversine_miles(start, end)
        steps = max(1, math.ceil(length / SAMPLE_SPACING_MILES))
        for step in range(steps):
            t = step / steps
            point = Point(
                start.latitude + (end.latitude - start.latitude) * t,
                start.longitude + (end.longitude - start.longitude) * t,
            )
            samples.append((point, total + length * t))
        total += length
    if vertices:
        samples.append((vertices[-1], total))
    return samples, total


def _cell(latitude, longitude):
    return math.floor(latitude / GRID_CELL_DEGREES), math.floor(longitude / GRID_CELL_DEGREES)


def _grid(stations):
    grid = {}
    for index, station in enumerate(stations):
        grid.setdefault(_cell(station.latitude, station.longitude), []).append(index)
    return grid


def _nearby_station_indexes(grid, point, radius_miles):
    row, column = _cell(point.latitude, point.longitude)
    cell_miles_lat = GRID_CELL_DEGREES * _MILES_PER_DEGREE_LATITUDE
    cell_miles_lon = cell_miles_lat * max(math.cos(math.radians(point.latitude)), 0.01)
    rows = math.ceil(radius_miles / cell_miles_lat)
    columns = math.ceil(radius_miles / cell_miles_lon)
    for dr in range(-rows, rows + 1):
        for dc in range(-columns, columns + 1):
            yield from grid.get((row + dr, column + dc), ())
