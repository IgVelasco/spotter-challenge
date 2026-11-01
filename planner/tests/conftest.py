import gzip
from io import StringIO
from pathlib import Path

import httpx
import pytest
from django.core.cache import cache
from django.core.management import call_command

from planner import services
from planner.routing import fetch_route

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


def recorded(name):
    path = FIXTURES / name
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt") as handle:
        return handle.read()


@pytest.fixture
def ors_replay(monkeypatch, settings):
    """Serve a recorded real ORS response instead of calling the network."""
    settings.ORS_API_KEY = "test-key"
    calls = []

    def use(fixture_name):
        body = recorded(fixture_name)

        def fake_fetch(start, finish):
            calls.append((start, finish))
            transport = httpx.MockTransport(lambda request: httpx.Response(200, text=body))
            return fetch_route(start, finish, transport=transport)

        monkeypatch.setattr(services, "fetch_route", fake_fetch)
        return calls

    return use


@pytest.fixture
def real_stations(db):
    call_command("import_stations", stdout=StringIO())
