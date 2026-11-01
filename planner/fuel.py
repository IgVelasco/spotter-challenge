"""Choose where to buy fuel, and how much, along a fixed route.

Pure calculation: no database, HTTP or geometry. The vehicle starts the trip at
mile 0 with a full tank; only fuel bought along the way is costed.

The plan minimises fuel cost plus a fixed cost per stop. Without the stop cost the
cheapest plan chases every small price drop with tiny top-ups (15+ stops coast to
coast); a modest stop cost trades ~1% more fuel spend for far fewer stops.

Method: dynamic programming over the fuel in the tank, measured in whole miles of
range. For each station we know the cheapest way to arrive with each fuel level;
buying is linear in price, so the best "arrive with f, leave with g" choice is a
running minimum and each station costs O(tank range) to process. Station miles are
rounded and the destination mile rounded up, so purchases are in 0.1-gallon steps
(at 10 mpg) and never short of the real distance.
"""

import math
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

VEHICLE_RANGE_MILES = 500
VEHICLE_MPG = 10
STOP_COST_USD = 10


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
    range_miles: int = VEHICLE_RANGE_MILES,
    mpg: float = VEHICLE_MPG,
    stop_cost: float = STOP_COST_USD,
) -> FuelPlan:
    if any(a.mile > b.mile for a, b in zip(stops, stops[1:], strict=False)):
        raise ValueError("Stops must be ordered by mile")
    miles = [round(s.mile) for s in stops]
    destination = math.ceil(total_miles - 1e-9)
    _check_legs_fit_in_tank(miles, destination, range_miles)

    # arrival[f]: cheapest cost to reach the current station with f miles of fuel.
    arrival = [math.inf] * (range_miles + 1)
    arrival[range_miles - (miles[0] if stops else destination)] = 0.0
    sources = []  # per station: departure level -> arrival level it was bought from
    for index, stop in enumerate(stops):
        departure, source = _buy_at_station(arrival, float(stop.price_per_gallon) / mpg, stop_cost)
        sources.append(source)
        next_mile = miles[index + 1] if index + 1 < len(stops) else destination
        arrival = _drive(departure, next_mile - miles[index])

    final_level = min(range(range_miles + 1), key=lambda level: arrival[level])
    return _purchases(stops, miles, destination, sources, final_level, mpg)


def _check_legs_fit_in_tank(miles, destination, range_miles):
    points = [0, *miles, destination]
    for leg, (start, end) in enumerate(zip(points, points[1:], strict=False)):
        if end - start > range_miles:
            origin = "the start" if leg == 0 else f"the station at mile {start}"
            target = "the destination" if leg == len(points) - 2 else "the station"
            raise InfeasibleRoute(f"Cannot reach {target} at mile {end} from {origin} on one tank")


def _buy_at_station(arrival, price_per_mile, stop_cost):
    """Cheapest cost to leave with each fuel level, and the arrival level it came from.

    Leaving with g: either buy nothing (arrived with g), or arrive with some f < g and
    buy g - f, costing arrival[f] + (g - f) * price + stop_cost. The best f for every g
    is the running minimum of arrival[f] - f * price.
    """
    departure, source = list(arrival), list(range(len(arrival)))
    best_base, best_level = math.inf, None
    for level, cost in enumerate(arrival):
        if best_level is not None:
            bought = best_base + level * price_per_mile + stop_cost
            if bought < departure[level]:
                departure[level], source[level] = bought, best_level
        if cost - level * price_per_mile < best_base:
            best_base, best_level = cost - level * price_per_mile, level
    return departure, source


def _drive(departure, leg_miles):
    return departure[leg_miles:] + [math.inf] * leg_miles


def _purchases(stops, miles, destination, sources, final_level, mpg):
    """Walk back from the destination to recover how much was bought at each stop."""
    plan = FuelPlan()
    level = final_level
    for index in range(len(stops) - 1, -1, -1):
        next_mile = miles[index + 1] if index + 1 < len(stops) else destination
        departure_level = level + next_mile - miles[index]
        level = sources[index][departure_level]
        bought_miles = departure_level - level
        if bought_miles:
            gallons = Decimal(bought_miles) / Decimal(str(mpg))
            cost = gallons * stops[index].price_per_gallon
            plan.purchases.append(Purchase(stops[index], float(gallons), cost))
    plan.purchases.reverse()
    return plan
