from django.db import DatabaseError
from django.shortcuts import render
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from planner import services
from planner.errors import log_request_failure, planning_error
from planner.models import Station
from planner.serializers import TripRequestSerializer, trip_payload


class PlanningThrottle(AnonRateThrottle):
    """Protects the free routing quota; shared by the JSON API and the map page."""

    scope = "planning"


@api_view(["GET"])
def health(request):
    """Ready only when the database answers and stations have been imported."""
    try:
        stations = Station.objects.count()
    except DatabaseError:
        return Response({"status": "unavailable", "reason": "Database unavailable"}, status=503)
    if stations == 0:
        return Response(
            {"status": "unavailable", "reason": "No stations: run manage.py import_stations"},
            status=503,
        )
    return Response({"status": "ok", "stations": stations})


class RoutePlanView(APIView):
    throttle_classes = [PlanningThrottle]

    def post(self, request):
        serializer = TripRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        price = data.get("starting_fuel_price_usd")
        trip = services.plan_trip(data["start"], data["finish"], starting_fuel_price=price)
        queries = (request.data["start"], request.data["finish"])
        return Response(trip_payload(trip, request, queries, price))


def route_map(request):
    """HTML map of the same plan the JSON API returns, for GET ?start=&finish=."""
    if not PlanningThrottle().allow_request(request, None):
        return _map_error(request, "Too many requests, try again in a minute", 429, "throttled")

    serializer = TripRequestSerializer(data=request.GET.dict())
    if not serializer.is_valid():
        message = "; ".join(
            f"{field}: {' '.join(str(m) for m in messages)}"
            for field, messages in serializer.errors.items()
        )
        return _map_error(request, message, 400, "invalid_request")

    data = serializer.validated_data
    price = data.get("starting_fuel_price_usd")
    try:
        trip = services.plan_trip(data["start"], data["finish"], starting_fuel_price=price)
    except Exception as error:
        mapping = planning_error(error)
        if mapping is None:
            raise
        status, code = mapping
        return _map_error(request, str(error), status, code, error)
    queries = (request.GET["start"], request.GET["finish"])
    return render(
        request, "planner/map.html", {"trip": trip_payload(trip, request, queries, price)}
    )


def _map_error(request, message, status, code, exc=None):
    log_request_failure(status, code, exc)
    return render(request, "planner/map.html", {"error": message}, status=status)
