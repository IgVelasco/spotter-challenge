from django.urls import path

from planner import views

urlpatterns = [
    path("health/", views.health, name="health"),
    path("route-plan/", views.RoutePlanView.as_view(), name="route-plan"),
    path("route-plan/map/", views.route_map, name="route-map"),
]
