"""Choose where to buy fuel, and how much, along a fixed route.

Pure calculation: no database, HTTP or geometry. The vehicle starts the trip with
an empty tank at mile 0, so a station must exist there.

Rule at each station: if a strictly cheaper station is within range, buy just
enough to reach the first one; otherwise buy enough to reach the destination, or
fill the tank if the destination is out of range. Fuel bought here is then never
more expensive than fuel that could have been bought later, which minimises the
total cost for the given ordered stations.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

VEHICLE_RANGE_MILES = 500
VEHICLE_MPG = 10

# Absorbs float rounding in mile/gallon arithmetic; far below any real quantity.
_TOLERANCE = 1e-9


class InfeasibleRoute(Exception):
    """The stations available cannot get the vehicle to the destination."""


@dataclass(frozen=True)
class FuelStop:
    mile: float
    price_per_gallon: Decimal
    ref: Any = None


@dataclass(frozen=True)
class Purchase:
    stop: FuelStop
    gallons: float
    cost: Decimal


@dataclass
class FuelPlan:
    purchases: list[Purchase] = field(default_factory=list)

    @property
    def total_gallons(self) -> float:
        return sum(p.gallons for p in self.purchases)

    @property
    def total_cost(self) -> Decimal:
        return sum((p.cost for p in self.purchases), Decimal(0))


def plan_fuel_stops(
    stops: list[FuelStop],
    total_miles: float,
    range_miles: float = VEHICLE_RANGE_MILES,
    mpg: float = VEHICLE_MPG,
) -> FuelPlan:
    _validate(stops, total_miles)
    plan = FuelPlan()
    fuel = 0.0
    for index, current in enumerate(stops):
        if index > 0:
            fuel -= _gallons_between(stops[index - 1], current, mpg, fuel)
        target_mile = _next_target_mile(stops, index, total_miles, range_miles)
        needed = min((target_mile - current.mile) / mpg, range_miles / mpg)
        gallons = needed - fuel
        if gallons > _TOLERANCE:
            plan.purchases.append(Purchase(current, gallons, _cost(gallons, current)))
            fuel += gallons
    if stops and total_miles - stops[-1].mile > fuel * mpg + _TOLERANCE:
        raise InfeasibleRoute(
            f"Cannot reach the destination at mile {total_miles:.0f} "
            f"from the last station at mile {stops[-1].mile:.0f}"
        )
    return plan


def _validate(stops, total_miles):
    if any(a.mile > b.mile for a, b in zip(stops, stops[1:], strict=False)):
        raise ValueError("Stops must be ordered by mile")
    if total_miles > 0 and (not stops or stops[0].mile > 0):
        raise InfeasibleRoute("No fuel station at the start of the route")


def _gallons_between(previous, current, mpg, fuel):
    gallons = (current.mile - previous.mile) / mpg
    if gallons > fuel + _TOLERANCE:
        raise InfeasibleRoute(
            f"Cannot reach the station at mile {current.mile:.0f} "
            f"from mile {previous.mile:.0f} on one tank"
        )
    return gallons


def _next_target_mile(stops, index, total_miles, range_miles):
    """Mile of the first strictly cheaper station in range, else the destination."""
    current = stops[index]
    for later in stops[index + 1 :]:
        if later.mile - current.mile > range_miles:
            break
        if later.price_per_gallon < current.price_per_gallon:
            return later.mile
    return total_miles


def _cost(gallons, stop):
    return Decimal(gallons).quantize(Decimal("0.000001")) * stop.price_per_gallon
