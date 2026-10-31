from django.urls import path

from planner import views

urlpatterns = [
    path("health/", views.health, name="health"),
]
