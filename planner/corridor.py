"""Find stations close to a route and where along it they are.

The route is resampled to a point every mile, stations are bucketed into a grid of
lat/lon cells, and each sample only measures stations in nearby cells. A station's
mile is that of its closest sample, scaled so the route's end matches the
provider's road distance.
"""

import bisect
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


def thin_line(coordinates, spacing_miles):
    """Drop vertices closer than spacing_miles to the last kept one; keep both ends."""
    if len(coordinates) < 3:
        return list(coordinates)
    kept = [coordinates[0]]
    for coordinate in coordinates[1:-1]:
        last = kept[-1]
        if haversine_miles(Point(last[1], last[0]), Point(coordinate[1], coordinate[0])) >= (
            spacing_miles
        ):
            kept.append(coordinate)
    kept.append(coordinates[-1])
    return kept


class RouteMeasure:
    """A route measured once, so stretches of it can be cut out cheaply.

    Miles are on the provider's scale (like CorridorStation.mile).
    """

    def __init__(self, coordinates, route_miles):
        self.coordinates = coordinates
        self._cumulative = [0.0]
        for a, b in zip(coordinates, coordinates[1:], strict=False):
            step = haversine_miles(Point(a[1], a[0]), Point(b[1], b[0]))
            self._cumulative.append(self._cumulative[-1] + step)
        polyline_miles = self._cumulative[-1]
        self._scale = polyline_miles / route_miles if route_miles else 1.0

    def stretch(self, start_mile, end_mile):
        """[longitude, latitude] pairs between two route miles, ends interpolated and clipped."""
        if len(self.coordinates) < 2:
            return list(self.coordinates)
        total = self._cumulative[-1]
        start = min(max(start_mile * self._scale, 0.0), total)
        end = min(max(end_mile * self._scale, start), total)
        last_segment = len(self.coordinates) - 2
        first = min(bisect.bisect_right(self._cumulative, start) - 1, last_segment)
        last = min(max(bisect.bisect_left(self._cumulative, end), first + 1), last_segment + 1)
        return [
            self._point_at(first, start),
            *self.coordinates[first + 1 : last],
            self._point_at(last - 1, end),
        ]

    def _point_at(self, segment, mile):
        a, b = self.coordinates[segment], self.coordinates[segment + 1]
        length = self._cumulative[segment + 1] - self._cumulative[segment]
        fraction = (mile - self._cumulative[segment]) / length if length else 0.0
        fraction = min(max(fraction, 0.0), 1.0)
        return [a[0] + (b[0] - a[0]) * fraction, a[1] + (b[1] - a[1]) * fraction]
