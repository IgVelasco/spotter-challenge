import itertools
import random
from decimal import Decimal

import pytest

from planner.fuel import FuelStop, InfeasibleRoute, plan_fuel_stops


def stop(mile, price, ref=None):
    return FuelStop(mile=mile, price_per_gallon=Decimal(str(price)), ref=ref or f"s{mile}")


def bought(plan):
    return [(p.stop.ref, p.gallons) for p in plan.purchases]


def test_trip_within_range_buys_nothing():
    plan = plan_fuel_stops([stop(100, 3)], total_miles=400)

    assert plan.purchases == []
    assert plan.total_cost == 0


def test_zero_distance_trip_costs_nothing():
    plan = plan_fuel_stops([], total_miles=0)

    assert plan.purchases == []
    assert plan.total_cost == 0


def test_fills_up_when_no_cheaper_station_is_in_range():
    plan = plan_fuel_stops([stop(300, 3), stop(600, 4)], total_miles=1000)

    # $3 at mile 300 is the cheapest ahead: fill the tank, then top up only what's left.
    assert bought(plan) == [("s300", 30), ("s600", 20)]
    assert plan.total_cost == Decimal("90") + Decimal("80")


def test_buys_just_enough_to_reach_first_cheaper_station():
    plan = plan_fuel_stops([stop(400, 4), stop(450, 3), stop(600, 2)], total_miles=1000)

    # Not "drive to the cheapest": the $3 station at 450 bridges to the $2 one for $110;
    # buying at $4 to reach $2 directly would cost $120.
    assert bought(plan) == [("s450", 10), ("s600", 40)]
    assert plan.total_cost == Decimal("110")


def test_skips_stations_that_are_not_needed():
    plan = plan_fuel_stops([stop(200, 5), stop(400, 5)], total_miles=500)

    assert plan.purchases == []


def test_equal_prices_buy_at_the_earlier_station():
    plan = plan_fuel_stops([stop(400, 3), stop(600, 3)], total_miles=900)

    assert bought(plan) == [("s400", 40)]
    assert plan.total_cost == Decimal("120")


def test_exactly_full_range_leg_is_feasible():
    plan = plan_fuel_stops([stop(500, 3)], total_miles=1000)

    assert bought(plan) == [("s500", 50)]


def test_gap_longer_than_range_is_infeasible():
    with pytest.raises(InfeasibleRoute, match="mile 501"):
        plan_fuel_stops([stop(501, 3)], total_miles=900)


def test_destination_out_of_range_from_last_station_is_infeasible():
    with pytest.raises(InfeasibleRoute, match="mile 100"):
        plan_fuel_stops([stop(100, 3)], total_miles=601)


def test_long_trip_without_stations_is_infeasible():
    with pytest.raises(InfeasibleRoute, match="destination"):
        plan_fuel_stops([], total_miles=501)


def test_fractional_distances_are_bought_exactly():
    plan = plan_fuel_stops([stop(500, "3.5")], total_miles=623.4)

    assert plan.total_gallons == pytest.approx(12.34)
    assert plan.total_cost == pytest.approx(Decimal("43.19"), abs=Decimal("0.01"))


def test_stations_must_be_ordered_by_mile():
    with pytest.raises(ValueError, match="ordered"):
        plan_fuel_stops([stop(100, 3), stop(0, 3)], total_miles=200)


def test_custom_vehicle_parameters():
    plan = plan_fuel_stops([stop(3, 1), stop(5, 2)], total_miles=10, range_miles=5, mpg=1)

    assert bought(plan) == [("s3", 3), ("s5", 2)]


def cheapest_cost_by_brute_force(stops, total_miles, capacity):
    """Independent check: try every whole-gallon purchase at every station (mpg=1)."""
    best = None
    choices = [range(capacity + 1)] * len(stops)
    for amounts in itertools.product(*choices):
        fuel, position, feasible = capacity, 0, True
        for s, amount in zip(stops, amounts, strict=True):
            fuel -= s.mile - position
            if fuel < 0:
                feasible = False
                break
            fuel += amount
            if fuel > capacity:
                feasible = False
                break
            position = s.mile
        fuel -= total_miles - position
        if feasible and fuel >= 0:
            cost = sum(a * s.price_per_gallon for s, a in zip(stops, amounts, strict=True))
            best = cost if best is None else min(best, cost)
    return best


def test_matches_brute_force_on_random_small_routes():
    rng = random.Random(42)
    feasible_cases = 0
    for _ in range(400):
        capacity = rng.randint(2, 5)
        total = rng.randint(1, 14)
        miles = sorted(rng.sample(range(0, total), rng.randint(0, min(4, total))))
        stops = [stop(m, rng.randint(1, 5)) for m in miles]

        expected = cheapest_cost_by_brute_force(stops, total, capacity)
        if expected is None:
            with pytest.raises(InfeasibleRoute):
                plan_fuel_stops(stops, total, range_miles=capacity, mpg=1)
        else:
            feasible_cases += 1
            plan = plan_fuel_stops(stops, total, range_miles=capacity, mpg=1)
            assert plan.total_cost == expected, (stops, total, capacity)

    assert feasible_cases > 100
