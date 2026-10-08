"""POST /api/v1/maps/directions against a fake Google Routes API."""

from __future__ import annotations

import json
from contextlib import ExitStack
from dataclasses import replace

import httpx
import pytest
from fastapi.testclient import TestClient

from bekhi_api import directions
from bekhi_api import main as main_mod
from bekhi_api.config import get_settings
from bekhi_api.contracts import validate_wire

ORIGIN = {"latitude": 47.9185, "longitude": 106.9177}
ROUTE = {
    "distanceMeters": 2350,
    "duration": "754s",
    "polyline": {"geoJsonLinestring": {"type": "LineString", "coordinates": [[106.9177, 47.9185], [106.92, 47.915], [106.93, 47.91]]}},
    "legs": [{
        "endLocation": {"latLng": {"latitude": 47.91, "longitude": 106.93}},
        "steps": [
            {"distanceMeters": 1200, "navigationInstruction": {"instructions": "Энхтайваны өргөн чөлөөгөөр зүүн тийш яв"}},
            {"distanceMeters": 1150, "navigationInstruction": {"instructions": "Баруун тийш эргэ"}},
            {"distanceMeters": 0},
        ],
    }],
}


@pytest.fixture
def maps_client(monkeypatch):
    """Builds an app whose Google Routes API is `handler`; closed after the test."""
    with ExitStack() as stack:

        def make(handler, key: str | None = "maps-key") -> TestClient:
            settings = replace(get_settings(), google_maps_api_key=key)
            monkeypatch.setattr(main_mod, "get_settings", lambda: settings)
            app = main_mod.create_app()
            client = stack.enter_context(TestClient(app))
            app.state.http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
            return client

        yield make


@pytest.fixture
def sent() -> list[httpx.Request]:
    return []


def test_route_matches_the_contract(maps_client, sent):
    def routes(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json={"routes": [ROUTE]})

    client = maps_client(routes)
    r = client.post("/api/v1/maps/directions", json={"origin": ORIGIN, "destination": "Сансар", "mode": "walking"})

    assert r.status_code == 200
    body = r.json()
    assert validate_wire("DirectionsResponse", body) == []
    assert body["distance_m"] == 2350 and body["duration_s"] == 754
    assert body["path"][0] == ORIGIN and body["destination"] == {"latitude": 47.91, "longitude": 106.93}
    assert [s["instruction"] for s in body["steps"]] == ["Энхтайваны өргөн чөлөөгөөр зүүн тийш яв", "Баруун тийш эргэ"]

    request = sent[0]
    assert request.headers["X-Goog-Api-Key"] == "maps-key"
    assert "routes.polyline.geoJsonLinestring" in request.headers["X-Goog-FieldMask"]
    payload = json.loads(request.content)
    assert payload["travelMode"] == "WALK" and "routingPreference" not in payload
    assert payload["origin"]["location"]["latLng"] == ORIGIN
    assert payload["destination"] == {"address": "Сансар"}


def test_driving_asks_for_traffic(maps_client, sent):
    def routes(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json={"routes": [ROUTE]})

    client = maps_client(routes)
    client.post("/api/v1/maps/directions", json={"origin": ORIGIN, "destination": "Зайсан"})
    payload = json.loads(sent[0].content)
    assert payload["travelMode"] == "DRIVE" and payload["routingPreference"] == "TRAFFIC_AWARE"


@pytest.mark.parametrize(
    ("google", "status", "message"),
    [
        (httpx.Response(200, json={}), 404, "зам олдсонгүй"),
        (httpx.Response(400, json={"error": {"status": "INVALID_ARGUMENT"}}), 404, "зам олдсонгүй"),
        (httpx.Response(403, json={"error": {"status": "PERMISSION_DENIED"}}), 502, "Routes API"),
        (httpx.Response(500), 502, "алдаа гарлаа"),
    ],
)
def test_google_errors_become_mongolian(maps_client, google, status, message):
    client = maps_client(lambda request: google)
    r = client.post("/api/v1/maps/directions", json={"origin": ORIGIN, "destination": "Сансар"})
    assert r.status_code == status
    assert r.json()["error"]["code"] == "maps_failed" and message in r.json()["error"]["message"]
    assert validate_wire("ApiError", r.json()) == []


def test_without_a_key_google_is_not_called(maps_client, sent):
    client = maps_client(lambda request: sent.append(request) or httpx.Response(200), key=None)
    r = client.post("/api/v1/maps/directions", json={"origin": ORIGIN, "destination": "Сансар"})
    assert r.status_code == 503 and "Google Maps" in r.json()["error"]["message"]
    assert sent == []


def test_impossible_coordinates_are_rejected(maps_client, sent):
    client = maps_client(lambda request: sent.append(request) or httpx.Response(200))
    r = client.post("/api/v1/maps/directions", json={"origin": {"latitude": 200, "longitude": 0}, "destination": "x"})
    assert r.status_code == 422 and sent == []


def route_to(lat: float, lng: float) -> dict:
    return {
        **ROUTE,
        "polyline": {"geoJsonLinestring": {"coordinates": [[ORIGIN["longitude"], ORIGIN["latitude"]], [lng, lat]]}},
        "legs": [{"endLocation": {"latLng": {"latitude": lat, "longitude": lng}}, "steps": []}],
    }


def test_a_name_google_cannot_place_is_looked_up_in_the_city(maps_client, sent):
    def routes(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        found = json.loads(request.content)["destination"]["address"] == "Сансар, Улаанбаатар"
        return httpx.Response(200, json={"routes": [ROUTE]} if found else {})

    r = maps_client(routes).post("/api/v1/maps/directions", json={"origin": ORIGIN, "destination": "Сансар"})
    assert r.status_code == 200
    assert [json.loads(s.content)["destination"]["address"] for s in sent] == ["Сансар", "Сансар, Улаанбаатар"]


def test_a_name_placed_abroad_is_looked_up_in_the_city(maps_client, sent):
    def routes(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        in_city = json.loads(request.content)["destination"]["address"].endswith("Улаанбаатар")
        # Bare "Зайсан" is Zaysan, Kazakhstan.
        return httpx.Response(200, json={"routes": [route_to(47.89, 106.91) if in_city else route_to(47.47, 84.87)]})

    r = maps_client(routes).post("/api/v1/maps/directions", json={"origin": ORIGIN, "destination": "Зайсан"})
    assert r.json()["destination"] == {"latitude": 47.89, "longitude": 106.91}
    assert len(sent) == 2


def test_another_mongolian_city_is_not_moved(maps_client, sent):
    def routes(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json={"routes": [route_to(49.48, 105.96)]})  # Darkhan

    r = maps_client(routes).post("/api/v1/maps/directions", json={"origin": ORIGIN, "destination": "Дархан"})
    assert r.json()["destination"] == {"latitude": 49.48, "longitude": 105.96}
    assert len(sent) == 1


def test_a_destination_naming_the_city_is_not_retried(maps_client, sent):
    def routes(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json={})

    r = maps_client(routes).post("/api/v1/maps/directions", json={"origin": ORIGIN, "destination": "Sansar, Ulaanbaatar"})
    assert r.status_code == 404 and len(sent) == 1


def test_long_routes_are_thinned_but_keep_both_ends():
    points = [[i, i] for i in range(12_001)]
    thinned = directions._thin(points, directions.MAX_PATH_POINTS)
    assert len(thinned) <= directions.MAX_PATH_POINTS
    assert thinned[0] == points[0] and thinned[-1] == points[-1]
