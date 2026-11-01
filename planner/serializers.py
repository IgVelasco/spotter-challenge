from decimal import ROUND_HALF_UP, Decimal
from urllib.parse import urlencode

from django.urls import reverse
from rest_framework import serializers

from planner.corridor import RouteMeasure, thin_line
from planner.fuel import STOP_COST_USD, VEHICLE_MPG, VEHICLE_RANGE_MILES
from planner.locations import LocationError, resolve_location
from planner.services import CORRIDOR_MILES

# The full ORS geometry has a point every few hundred feet (~500 KB coast to coast).
RESPONSE_LINE_SPACING_MILES = 0.5
# Stations are located at their town's centre, so each stop comes with the stretch of
# route around it where the driver should look for the station.
STOP_STRETCH_HALF_MILES = 5
STRETCH_LINE_SPACING_MILES = 0.25
MAX_LOCATION_TEXT_LENGTH = 255


class LocationField(serializers.Field):
    default_error_messages = {
        "invalid": "{message}",
        "too_long": f"Use at most {MAX_LOCATION_TEXT_LENGTH} characters.",
    }

    def to_internal_value(self, data):
        if isinstance(data, str) and len(data) > MAX_LOCATION_TEXT_LENGTH:
            self.fail("too_long")
        try:
            return resolve_location(data)
        except LocationError as error:
            self.fail("invalid", message=str(error))


class TripRequestSerializer(serializers.Serializer):
    start = LocationField(help_text='"City, ST", "lat,lon" or {"latitude", "longitude"}')
    finish = LocationField(help_text='"City, ST", "lat,lon" or {"latitude", "longitude"}')
    starting_fuel_price_usd = serializers.DecimalField(
        max_digits=6, decimal_places=3, min_value=Decimal("0.001"), required=False
    )

    def validate(self, attrs):
        unknown = set(self.initial_data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError({field: ["Unknown field."] for field in unknown})
        return attrs


def _money(value):
    return str(Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _point_text(point):
    return f"{point.latitude},{point.longitude}"


def map_url(request, trip, starting_fuel_price):
    query = {"start": _point_text(trip.start), "finish": _point_text(trip.finish)}
    if starting_fuel_price is not None:
        query["starting_fuel_price_usd"] = f"{starting_fuel_price.normalize():f}"
    return request.build_absolute_uri(f"{reverse('route-map')}?{urlencode(query)}")


def _endpoint(query, point):
    return {"query": query, "latitude": point.latitude, "longitude": point.longitude}


def trip_payload(trip, request, queries, starting_fuel_price=None):
    """queries: the start and finish exactly as the caller sent them."""
    start_query, finish_query = queries
    return {
        "start": _endpoint(start_query, trip.start),
        "finish": _endpoint(finish_query, trip.finish),
        "route": {
            "distance_miles": round(trip.route.distance_miles, 1),
            "duration_hours": round(trip.route.duration_seconds / 3600, 2),
            "geometry": {
                "type": "LineString",
                "coordinates": thin_line(trip.route.coordinates, RESPONSE_LINE_SPACING_MILES),
            },
        },
        "fuel_stops": _stops_payload(trip),
        "fuel_summary": _summary_payload(trip),
        "assumptions": {
            "vehicle_range_miles": VEHICLE_RANGE_MILES,
            "miles_per_gallon": VEHICLE_MPG,
            "starting_tank": "full",
            "stop_cost_usd": STOP_COST_USD,
            "max_miles_off_route": CORRIDOR_MILES,
            "station_location": "centre of the station's town",
            "price_rule": "highest listed price per station",
        },
        "routing_api_calls": trip.routing_calls,
        "map_url": map_url(request, trip, starting_fuel_price),
        "attribution": trip.route.attribution,
    }


def _stops_payload(trip):
    if not trip.stops:
        return []
    measure = RouteMeasure(trip.route.coordinates, trip.route.distance_miles)
    return [_stop_payload(stop, trip.route, measure) for stop in trip.stops]


def _stop_payload(stop, route, measure):
    station = stop.station
    return {
        "opis_id": station.opis_id,
        "name": station.name,
        "address": station.address,
        "city": station.city,
        "state": station.state,
        "latitude": station.latitude,
        "longitude": station.longitude,
        "route_mile": round(stop.mile, 1),
        "miles_off_route": round(stop.offset_miles, 1),
        "price_per_gallon": str(station.price_per_gallon.quantize(Decimal("0.001"))),
        "gallons": round(stop.gallons, 1),
        "cost_usd": _money(stop.cost),
        "route_stretch": _stretch_payload(stop.mile, route, measure),
    }


def _stretch_payload(mile, route, measure):
    start = max(mile - STOP_STRETCH_HALF_MILES, 0.0)
    end = min(mile + STOP_STRETCH_HALF_MILES, route.distance_miles)
    coordinates = measure.stretch(start, end)
    return {
        "start_mile": round(start, 1),
        "end_mile": round(end, 1),
        "geometry": {
            "type": "LineString",
            "coordinates": thin_line(coordinates, STRETCH_LINE_SPACING_MILES),
        },
    }


def _summary_payload(trip):
    # Line items are rounded to cents first so the displayed total adds up.
    purchased = sum((Decimal(_money(stop.cost)) for stop in trip.stops), Decimal(0))
    starting = None if trip.starting_fuel_cost is None else Decimal(_money(trip.starting_fuel_cost))
    return {
        "gallons_used": round(trip.gallons_used, 1),
        "gallons_purchased": round(trip.purchased_gallons, 1),
        "starting_fuel_gallons_used": round(trip.starting_fuel_gallons, 1),
        "fuel_purchased_cost_usd": _money(purchased),
        "starting_fuel_cost_usd": None if starting is None else _money(starting),
        "total_fuel_cost_usd": _money(purchased + (starting or 0)),
    }
