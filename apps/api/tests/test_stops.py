"""POST /api/v1/maps/stops/nearby against a fake Google Places API."""

from __future__ import annotations

import json
from contextlib import ExitStack
from dataclasses import replace

import httpx
import pytest
from fastapi.testclient import TestClient

from bekhi_api import main as main_mod
from bekhi_api import stops
from bekhi_api.config import get_settings
from bekhi_api.contracts import validate_wire

ORIGIN = {"latitude": 47.9185, "longitude": 106.9176}
PLACES = [
    {"id": "far", "displayName": {"text": "МУБИС"}, "location": {"latitude": 47.9198, "longitude": 106.9232}},
    {"id": "near", "displayName": {"text": "Сүхбаатарын талбайн төв зогсоол"}, "location": {"latitude": 47.9179, "longitude": 106.9178}},
    {"id": "nameless", "displayName": {"text": " "}, "location": {"latitude": 47.918, "longitude": 106.917}},
    {"id": "nowhere", "displayName": {"text": "Цэцэг төв"}},
]


@pytest.fixture
def stops_client(monkeypatch):
    with ExitStack() as stack:

        def make(handler, key: str | None = "maps-key") -> TestClient:
            settings = replace(get_settings(), google_maps_api_key=key)
            monkeypatch.setattr(main_mod, "get_settings", lambda: settings)
            app = main_mod.create_app()
            client = stack.enter_context(TestClient(app))
            app.state.http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
            return client

        yield make


def test_nearby_stops_nearest_first(stops_client):
    sent: list[httpx.Request] = []

    def places(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json={"places": PLACES})

    r = stops_client(places).post("/api/v1/maps/stops/nearby", json={"origin": ORIGIN, "radius_m": 500})

    assert r.status_code == 200
    body = r.json()
    assert validate_wire("NearbyStopsResponse", body) == []
    assert [s["id"] for s in body["stops"]] == ["near", "far"]
    assert 60 < body["stops"][0]["distance_m"] < 80

    request = sent[0]
    assert request.headers["X-Goog-Api-Key"] == "maps-key"
    payload = json.loads(request.content)
    assert "bus_stop" in payload["includedTypes"] and payload["rankPreference"] == "DISTANCE"
    assert payload["locationRestriction"]["circle"] == {"center": ORIGIN, "radius": 500.0}


def test_no_stops_nearby_is_an_empty_list(stops_client):
    r = stops_client(lambda request: httpx.Response(200, json={})).post("/api/v1/maps/stops/nearby", json={"origin": ORIGIN})
    assert r.status_code == 200 and r.json() == {"stops": []}


@pytest.mark.parametrize(
    ("google", "message"),
    [(httpx.Response(403), "Places API"), (httpx.Response(500), "буудлуудыг")],
)
def test_google_errors_become_mongolian(stops_client, google, message):
    r = stops_client(lambda request: google).post("/api/v1/maps/stops/nearby", json={"origin": ORIGIN})
    assert r.status_code == 502 and message in r.json()["error"]["message"]
    assert validate_wire("ApiError", r.json()) == []


def test_without_a_key_google_is_not_called(stops_client):
    sent: list[httpx.Request] = []
    client = stops_client(lambda request: sent.append(request) or httpx.Response(200), key=None)
    r = client.post("/api/v1/maps/stops/nearby", json={"origin": ORIGIN})
    assert r.status_code == 503 and sent == []


@pytest.mark.parametrize("radius", [50, 5000])
def test_radius_is_bounded(stops_client, radius):
    sent: list[httpx.Request] = []
    client = stops_client(lambda request: sent.append(request) or httpx.Response(200))
    r = client.post("/api/v1/maps/stops/nearby", json={"origin": ORIGIN, "radius_m": radius})
    assert r.status_code == 422 and sent == []


def test_distance_is_in_metres():
    assert round(stops.distance_m(ORIGIN, {"latitude": 47.9275, "longitude": 106.9176})) == 1001
