"""Turn trip endpoints into coordinates without calling any external API."""

from functools import cache

from django.conf import settings

from planner.geodata import US_STATE_CODES, PlaceIndex, Point, load_place_records


class LocationError(ValueError):
    """An endpoint can't be resolved or is outside the US; message is user-facing."""


# Coarse boxes (south, north, west, east) for the contiguous US, Alaska and Hawaii.
_US_BOUNDS = (
    (24.4, 49.4, -124.9, -66.9),
    (51.2, 71.5, -180.0, -129.9),
    (18.9, 22.3, -160.3, -154.8),
)


@cache
def place_index() -> PlaceIndex:
    return PlaceIndex(load_place_records(settings.US_PLACES_CSV))


def resolve_city(text: str) -> Point:
    city, _, state = text.rpartition(",")
    city, state = city.strip(), state.strip().upper()
    if not city or not state:
        raise LocationError(f'Use the format "City, ST" (got "{text}")')
    if state not in US_STATE_CODES:
        raise LocationError(f'"{state}" is not a two-letter US state code')
    place = place_index().resolve(city, state)
    if place is None:
        raise LocationError(f'Unknown US city "{city}, {state}"')
    return Point(place.latitude, place.longitude)


def check_in_us(point: Point) -> None:
    for south, north, west, east in _US_BOUNDS:
        if south <= point.latitude <= north and west <= point.longitude <= east:
            return
    raise LocationError(f"({point.latitude}, {point.longitude}) is outside the United States")
