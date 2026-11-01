from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from planner import views

urlpatterns = [
    path("health/", views.health, name="health"),
    path("route-plan/", views.RoutePlanView.as_view(), name="route-plan"),
    path("route-plan/map/", views.route_map, name="route-map"),
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
]
