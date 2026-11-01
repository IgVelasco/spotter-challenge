"""One JSON error shape for the whole API: {"error": {"code", "message", "details"?}}."""

import json
import logging

from django.http import JsonResponse
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler

from planner.fuel import InfeasibleRoute
from planner.routing import RouteNotFound, RoutingUnavailable

logger = logging.getLogger(__name__)

PLANNING_ERRORS = {
    RouteNotFound: (status.HTTP_422_UNPROCESSABLE_ENTITY, "route_not_found"),
    InfeasibleRoute: (status.HTTP_422_UNPROCESSABLE_ENTITY, "no_feasible_fuel_plan"),
    RoutingUnavailable: (status.HTTP_502_BAD_GATEWAY, "routing_unavailable"),
}


def error_body(code, message, details=None):
    error = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return {"error": error}


def planning_error(exc):
    """(status, code) for a known planning failure, or None."""
    for error_class, mapping in PLANNING_ERRORS.items():
        if isinstance(exc, error_class):
            return mapping
    return None


def api_exception_handler(exc, context):
    mapping = planning_error(exc)
    if mapping is not None:
        status_code, code = mapping
        response = Response(error_body(code, str(exc)), status=status_code)
    else:
        response = exception_handler(exc, context)
        if response is None:
            return None
        if isinstance(exc, ValidationError):
            response.data = error_body("invalid_request", "The request is invalid", exc.detail)
        else:
            response.data = error_body(exc.default_code, str(exc.detail))
    logger.warning(
        json.dumps(
            {
                "event": "request_failed",
                "status": response.status_code,
                "code": response.data["error"]["code"],
            }
        )
    )
    return response


def not_found(request, exception=None):
    return JsonResponse(error_body("not_found", "Not found"), status=404)


def server_error(request):
    return JsonResponse(error_body("server_error", "Internal server error"), status=500)
