import pytest

from planner.geodata import Point
from planner.locations import LocationError, check_in_us, resolve_city


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Chicago, IL", (41.84, -87.68)),
        ("chicago,il", (41.84, -87.68)),
        ("  New York ,  NY ", (40.66, -73.94)),
        ("Saint Louis, MO", (38.64, -90.25)),
        ("Oklahoma City, OK", (35.47, -97.51)),
    ],
)
def test_resolves_real_us_cities(text, expected):
    point = resolve_city(text)

    assert (point.latitude, point.longitude) == pytest.approx(expected, abs=0.05)


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("Chicago", "City, ST"),
        ("Chicago, Illinois", "two-letter"),
        ("Toronto, ON", "two-letter"),
        ("Atlantis, NV", "Atlantis, NV"),
        (", IL", "City, ST"),
    ],
)
def test_rejects_unresolvable_text_with_helpful_message(text, message):
    with pytest.raises(LocationError, match=message):
        resolve_city(text)


@pytest.mark.parametrize(
    "point",
    [
        Point(41.88, -87.63),  # Chicago
        Point(61.22, -149.90),  # Anchorage
        Point(21.31, -157.86),  # Honolulu
    ],
)
def test_us_points_pass(point):
    check_in_us(point)


@pytest.mark.parametrize(
    "point",
    [
        Point(48.86, 2.35),  # Paris
        Point(19.43, -99.13),  # Mexico City
        Point(53.55, -113.49),  # Edmonton
        Point(91, 0),
    ],
)
def test_non_us_points_are_rejected(point):
    with pytest.raises(LocationError, match="United States"):
        check_in_us(point)
