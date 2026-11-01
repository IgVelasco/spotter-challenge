"""Plan a trip: route it, find stations along it, and choose where to buy fuel."""

from dataclasses import dataclass
from decimal import Decimal

from planner.corridor import stations_along_route
from planner.fuel import VEHICLE_MPG, VEHICLE_RANGE_MILES, FuelStop, plan_fuel_stops
from planner.geodata import Point
from planner.models import Station
from planner.routing import Route, fetch_route

# Stations are placed at their town's centre, which can be a few miles off the highway.
CORRIDOR_MILES = 10
# Plan as if the tank were smaller so a detour to a station and back always fits.
PLANNING_RANGE_MILES = VEHICLE_RANGE_MILES - 2 * CORRIDOR_MILES


@dataclass(frozen=True)
class PlannedStop:
    station: Station
    mile: float
    offset_miles: float
    gallons: float
    cost: Decimal


@dataclass(frozen=True)
class TripPlan:
    start: Point
    finish: Point
    route: Route
    stops: list[PlannedStop]
    gallons_used: float
    purchased_gallons: float
    purchased_cost: Decimal
    starting_fuel_gallons: float
    starting_fuel_cost: Decimal | None
    total_fuel_cost: Decimal
    routing_calls: int


def plan_trip(start: Point, finish: Point, starting_fuel_price: Decimal | None = None):
    """Raises LocationError, RoutingError or InfeasibleRoute with user-facing messages."""
    if start == finish:
        route, routing_calls = _stationary_route(start), 0
    else:
        route, routing_calls = fetch_route(start, finish), 1

    candidates = []
    if route.distance_miles > PLANNING_RANGE_MILES:
        candidates = stations_along_route(
            route.coordinates, route.distance_miles, _stations(), CORRIDOR_MILES
        )
    plan = plan_fuel_stops(
        [FuelStop(c.mile, c.station.price_per_gallon, c) for c in candidates],
        route.distance_miles,
        range_miles=PLANNING_RANGE_MILES,
    )
    stops = [
        PlannedStop(p.stop.ref.station, p.stop.ref.mile, p.stop.ref.offset_miles, p.gallons, p.cost)
        for p in plan.purchases
    ]

    gallons_used = route.distance_miles / VEHICLE_MPG
    starting_fuel_gallons = max(gallons_used - plan.total_gallons, 0.0)
    starting_fuel_cost = None
    if starting_fuel_price is not None:
        starting_fuel_cost = Decimal(str(round(starting_fuel_gallons, 4))) * starting_fuel_price

    return TripPlan(
        start=start,
        finish=finish,
        route=route,
        stops=stops,
        gallons_used=gallons_used,
        purchased_gallons=plan.total_gallons,
        purchased_cost=plan.total_cost,
        starting_fuel_gallons=starting_fuel_gallons,
        starting_fuel_cost=starting_fuel_cost,
        total_fuel_cost=plan.total_cost + (starting_fuel_cost or 0),
        routing_calls=routing_calls,
    )


def _stations():
    return list(
        Station.objects.only(
            "opis_id",
            "name",
            "address",
            "city",
            "state",
            "price_per_gallon",
            "latitude",
            "longitude",
        )
    )


def _stationary_route(point):
    coordinate = [point.longitude, point.latitude]
    return Route([coordinate, coordinate], distance_miles=0.0, duration_seconds=0.0, attribution="")
