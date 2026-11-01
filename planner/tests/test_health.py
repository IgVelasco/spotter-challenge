import pytest
from django.db import DatabaseError

from planner.models import Station


@pytest.mark.django_db
def test_health_reports_ok_with_station_count(real_stations, client):
    response = client.get("/api/v1/health/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "stations": 6435}


@pytest.mark.django_db
def test_health_is_unavailable_without_stations(client):
    response = client.get("/api/v1/health/")

    assert response.status_code == 503
    assert response.json()["status"] == "unavailable"
    assert "import_stations" in response.json()["reason"]


@pytest.mark.django_db
def test_health_is_unavailable_when_the_database_fails(client, monkeypatch):
    def broken_count():
        raise DatabaseError("connection refused")

    monkeypatch.setattr(Station.objects, "count", broken_count)

    response = client.get("/api/v1/health/")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "reason": "Database unavailable"}
