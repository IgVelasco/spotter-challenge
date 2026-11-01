from django.urls import include, path

urlpatterns = [
    path("api/v1/", include("planner.urls")),
]

handler404 = "planner.errors.not_found"
handler500 = "planner.errors.server_error"
