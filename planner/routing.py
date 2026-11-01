"""Driving routes from openrouteservice (ORS): one directions call per trip."""

from dataclasses import dataclass

import httpx
from django.conf import settings
from django.core.cache import cache

from planner.geodata import Point

ORS_DIRECTIONS_URL = "https://api.heigit.org/openrouteservice/v2/directions/driving-car/geojson"
REQUEST_TIMEOUT_SECONDS = 15
ROUTE_CACHE_SECONDS = 24 * 60 * 60
METERS_PER_MILE = 1609.344


class RoutingError(Exception):
    """Base class for routing failures; messages are safe to show to API clients."""


class RouteNotFound(RoutingError):
    """ORS could not route between the given points (e.g. no road nearby)."""


class RoutingUnavailable(RoutingError):
    """ORS failed, timed out, rejected the key or returned an unexpected body."""


@dataclass(frozen=True)
class Route:
    coordinates: list[list[float]]  # GeoJSON order: [longitude, latitude]
    distance_miles: float
    duration_seconds: float
    attribution: str


def fetch_route(origin: Point, destination: Point, transport=None) -> Route:
    key = "route:" + ":".join(f"{p.latitude:.5f},{p.longitude:.5f}" for p in (origin, destination))
    route = cache.get(key)
    if route is None:
        route = _parse(_request(origin, destination, transport))
        cache.set(key, route, ROUTE_CACHE_SECONDS)
    return route


def _request(origin, destination, transport):
    if not settings.ORS_API_KEY:
        raise RoutingUnavailable("Routing is not configured: set ORS_API_KEY")
    body = {"coordinates": [[p.longitude, p.latitude] for p in (origin, destination)]}
    try:
        with httpx.Client(transport=transport, timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = client.post(
                ORS_DIRECTIONS_URL, json=body, headers={"Authorization": settings.ORS_API_KEY}
            )
    except httpx.TimeoutException as error:
        raise RoutingUnavailable("The routing provider timed out") from error
    except httpx.HTTPError as error:
        raise RoutingUnavailable(
            f"Could not reach the routing provider ({type(error).__name__})"
        ) from error

    if response.status_code == 404:
        raise RouteNotFound(_ors_error_message(response) or "No route found between the points")
    if response.status_code != 200:
        raise RoutingUnavailable(f"The routing provider returned HTTP {response.status_code}")
    return response


def _parse(response):
    try:
        body = response.json()
        feature = body["features"][0]
        summary = feature["properties"]["summary"]
        return Route(
            coordinates=feature["geometry"]["coordinates"],
            distance_miles=summary["distance"] / METERS_PER_MILE,
            duration_seconds=summary["duration"],
            attribution=body.get("metadata", {}).get("attribution", "openrouteservice.org"),
        )
    except (ValueError, KeyError, IndexError, TypeError) as error:
        raise RoutingUnavailable("The routing provider returned an unexpected response") from error


def _ors_error_message(response):
    try:
        return response.json()["error"]["message"]
    except (ValueError, KeyError, TypeError):
        return None
