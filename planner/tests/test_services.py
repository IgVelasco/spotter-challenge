from decimal import Decimal

import pytest

from planner import services
from planner.fuel import VEHICLE_RANGE_MILES, InfeasibleRoute
from planner.geodata import Point

CHICAGO = Point(41.837045, -87.684939)
MILWAUKEE = Point(43.0389, -87.9065)
DENVER = Point(39.76185, -104.881105)


def legs(trip):
    miles = [0, *(stop.mile for stop in trip.stops), trip.route.distance_miles]
    return [b - a for a, b in zip(miles, miles[1:], strict=False)]


def test_short_trip_needs_no_fuel_stops(ors_replay, real_stations):
    calls = ors_replay("ors_chicago_milwaukee.json")

    trip = services.plan_trip(CHICAGO, MILWAUKEE)

    assert len(calls) == 1
    assert trip.stops == []
    assert trip.purchased_cost == 0
    assert trip.total_fuel_cost == 0
    assert trip.gallons_used == pytest.approx(9.21, abs=0.01)
    assert trip.starting_fuel_cost is None


def test_starting_fuel_price_costs_the_gallons_burned_from_the_start_tank(
    ors_replay, real_stations
):
    ors_replay("ors_chicago_milwaukee.json")

    trip = services.plan_trip(CHICAGO, MILWAUKEE, starting_fuel_price=Decimal("3.50"))

    assert trip.starting_fuel_gallons == pytest.approx(9.21, abs=0.01)
    assert trip.starting_fuel_cost == pytest.approx(Decimal("32.24"), abs=Decimal("0.01"))
    assert trip.total_fuel_cost == trip.starting_fuel_cost


def test_long_trip_buys_fuel_at_real_stations_along_the_route(ors_replay, real_stations):
    calls = ors_replay("ors_chicago_denver.json.gz")

    trip = services.plan_trip(CHICAGO, DENVER, starting_fuel_price=Decimal("3.00"))

    assert len(calls) == 1
    assert trip.route.distance_miles == pytest.approx(1000.7, abs=0.1)
    assert len(trip.stops) >= 2
    assert all(leg <= VEHICLE_RANGE_MILES for leg in legs(trip))
    assert all(stop.offset_miles <= services.CORRIDOR_MILES for stop in trip.stops)
    assert [s.mile for s in trip.stops] == sorted(s.mile for s in trip.stops)
    assert trip.purchased_cost == sum(stop.cost for stop in trip.stops)
    assert trip.purchased_gallons + trip.starting_fuel_gallons == pytest.approx(
        trip.gallons_used, abs=0.2
    )
    assert trip.total_fuel_cost == trip.purchased_cost + trip.starting_fuel_cost


def test_trip_is_infeasible_without_stations(ors_replay, db):
    ors_replay("ors_chicago_denver.json.gz")

    with pytest.raises(InfeasibleRoute):
        services.plan_trip(CHICAGO, DENVER)


def test_same_start_and_finish_skips_the_routing_call(ors_replay, db):
    calls = ors_replay("ors_chicago_milwaukee.json")

    trip = services.plan_trip(CHICAGO, CHICAGO)

    assert calls == []
    assert trip.route.distance_miles == 0
    assert trip.stops == []
    assert trip.routing_calls == 0
