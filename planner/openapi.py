"""OpenAPI documentation for the planning endpoint: examples and error responses."""

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiExample, OpenApiResponse, inline_serializer
from rest_framework import serializers

LOCATION_SCHEMA = {
    "oneOf": [
        {
            "type": "string",
            "maxLength": 255,
            "description": '"City, ST" or "lat,lon"',
            "example": "Chicago, IL",
        },
        {
            "type": "object",
            "properties": {
                "latitude": {"type": "number", "example": 41.8781},
                "longitude": {"type": "number", "example": -87.6298},
            },
            "required": ["latitude", "longitude"],
        },
    ]
}

ERROR = inline_serializer(
    name="Error",
    fields={
        "error": inline_serializer(
            name="ErrorBody",
            fields={
                "code": serializers.CharField(),
                "message": serializers.CharField(),
                "details": serializers.DictField(required=False),
            },
        )
    },
)


def _error(description, code, message, details=None):
    body = {"error": {"code": code, "message": message}}
    if details is not None:
        body["error"]["details"] = details
    return OpenApiResponse(
        response=ERROR,
        description=description,
        examples=[OpenApiExample(code, value=body, response_only=True)],
    )


REQUEST_EXAMPLES = [
    OpenApiExample(
        "Cities", value={"start": "Chicago, IL", "finish": "Denver, CO"}, request_only=True
    ),
    OpenApiExample(
        "Coordinates and starting fuel price",
        value={
            "start": {"latitude": 47.6062, "longitude": -122.3321},
            "finish": "25.7617,-80.1918",
            "starting_fuel_price_usd": "3.50",
        },
        request_only=True,
    ),
]

# Real response for Chicago -> Denver with starting_fuel_price_usd 3.50; geometry shortened.
TRIP_PLAN_EXAMPLE = {
    "start": {"query": "Chicago, IL", "latitude": 41.837045, "longitude": -87.684939},
    "finish": {"query": "Denver, CO", "latitude": 39.76185, "longitude": -104.881105},
    "route": {
        "distance_miles": 1000.7,
        "duration_hours": 15.93,
        "geometry": {"type": "LineString", "coordinates": [[-87.684892, 41.837051]]},
    },
    "fuel_stops": [
        {
            "opis_id": 70467,
            "name": "QUIKTRIP #598",
            "address": "I-80, EXIT 439, SR-370",
            "city": "Omaha",
            "state": "NE",
            "latitude": 41.262705,
            "longitude": -96.053475,
            "route_mile": 470.5,
            "miles_off_route": 2.7,
            "price_per_gallon": "2.927",
            "gallons": 7.8,
            "cost_usd": "22.83",
            "route_stretch": {
                "start_mile": 465.5,
                "end_mile": 475.5,
                "geometry": {"type": "LineString", "coordinates": [[-96.1, 41.2]]},
            },
        }
    ],
    "fuel_summary": {
        "gallons_used": 100.1,
        "gallons_purchased": 52.1,
        "starting_fuel_gallons_used": 48.0,
        "fuel_purchased_cost_usd": "146.83",
        "starting_fuel_cost_usd": "167.91",
        "total_fuel_cost_usd": "314.74",
    },
    "assumptions": {
        "vehicle_range_miles": 500,
        "miles_per_gallon": 10,
        "starting_tank": "full",
        "stop_cost_usd": 10,
        "max_miles_off_route": 10,
        "station_location": "centre of the station's town",
        "price_rule": "highest listed price per station",
    },
    "routing_api_calls": 1,
    "map_url": "http://localhost:8000/api/v1/route-plan/map/?start=41.837045%2C-87.684939"
    "&finish=39.76185%2C-104.881105&starting_fuel_price_usd=3.5",
    "attribution": "openrouteservice.org | OpenStreetMap contributors",
}

ROUTE_PLAN_DESCRIPTION = """Plan a trip's fuel stops for a vehicle with a 500-mile range at 10 mpg.

Makes one routing call per trip (repeats are cached). The vehicle starts with a full
tank; `total_fuel_cost_usd` is the fuel bought along the route, plus the starting fuel
burned when `starting_fuel_price_usd` is given. Each stop's coordinates are its town's
centre; `route_stretch` is the part of the route where to look for the station.
`map_url` opens the same plan on an HTML map (not part of this JSON API)."""

ROUTE_PLAN_RESPONSES = {
    200: OpenApiResponse(
        response=OpenApiTypes.OBJECT,
        description="Route, fuel stops and costs",
        examples=[OpenApiExample("Chicago to Denver", value=TRIP_PLAN_EXAMPLE, response_only=True)],
    ),
    400: _error(
        "Invalid input",
        "invalid_request",
        "The request is invalid",
        {"start": ['Unknown US city "Atlantis, NV"']},
    ),
    422: _error(
        "No route, or no feasible fuel plan",
        "no_feasible_fuel_plan",
        "Cannot reach the station at mile 612 from the start on one tank",
    ),
    429: _error("Too many plans from this client", "throttled", "Request was throttled."),
    502: _error("Routing provider failed", "routing_unavailable", "The routing provider timed out"),
}

HEALTH_RESPONSES = {
    200: OpenApiResponse(
        OpenApiTypes.OBJECT,
        examples=[OpenApiExample("Ready", value={"status": "ok", "stations": 6435})],
    ),
    503: OpenApiResponse(
        OpenApiTypes.OBJECT,
        examples=[
            OpenApiExample(
                "No stations",
                value={
                    "status": "unavailable",
                    "reason": "No stations: run manage.py import_stations",
                },
            )
        ],
    ),
}
