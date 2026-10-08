"""In-app directions from the Google Routes API (computeRoutes).

The key stays on this server: the app sends where the phone is and where the user wants to go,
and gets back the route to draw. Logs never contain either place.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)

URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
TRAVEL_MODES = {"driving": "DRIVE", "walking": "WALK", "transit": "TRANSIT"}
# Only what the app draws and shows: Google bills by the fields asked for.
FIELD_MASK = ",".join([
    "routes.distanceMeters",
    "routes.duration",
    "routes.polyline.geoJsonLinestring",
    "routes.legs.endLocation",
    "routes.legs.steps.distanceMeters",
    "routes.legs.steps.navigationInstruction.instructions",
])
MAX_PATH_POINTS = 5000
MAX_STEPS = 200
MAX_INSTRUCTION_CHARS = 500

# HTTP status -> error code. A destination Google cannot place is a 400 or a response without routes.
ERRORS = {400: "ROUTE_NOT_FOUND", 404: "ROUTE_NOT_FOUND", 401: "MAPS_KEY_INVALID", 403: "MAPS_KEY_INVALID"}


# A bare place name can mean somewhere else entirely: Google finds no "Сансар", and puts "Зайсан"
# in Kazakhstan (2,600 km away). Users here mean their own city, so such names are retried with it.
HOME_CITY = "Улаанбаатар"
HOME_CITY_NAMES = ("улаанбаатар", "ulaanbaatar", "ulan bator")
# lat min, lat max, lng min, lng max
MONGOLIA = (41.5, 52.2, 87.7, 120.0)


class DirectionsError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


async def compute_route(
    http: httpx.AsyncClient, api_key: str, origin: dict[str, float], destination: str, mode: str
) -> dict[str, Any]:
    in_city = f"{destination}, {HOME_CITY}"
    names_city = any(n in destination.lower() for n in HOME_CITY_NAMES)
    try:
        route = await _request(http, api_key, origin, destination, mode)
    except DirectionsError as e:
        if e.code != "ROUTE_NOT_FOUND" or names_city:
            raise
        return await _request(http, api_key, origin, in_city, mode)
    if not names_city and _in_mongolia(origin) and not _in_mongolia(route["destination"]):
        try:
            return await _request(http, api_key, origin, in_city, mode)
        except DirectionsError:
            pass  # really abroad
    return route


def _in_mongolia(p: dict[str, float]) -> bool:
    lat_min, lat_max, lng_min, lng_max = MONGOLIA
    return lat_min <= p["latitude"] <= lat_max and lng_min <= p["longitude"] <= lng_max


async def _request(
    http: httpx.AsyncClient, api_key: str, origin: dict[str, float], destination: str, mode: str
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "origin": {"location": {"latLng": origin}},
        "destination": {"address": destination},
        "travelMode": TRAVEL_MODES[mode],
        "polylineEncoding": "GEO_JSON_LINESTRING",
        "languageCode": "mn",
        "regionCode": "mn",
        "units": "METRIC",
    }
    if mode == "driving":
        body["routingPreference"] = "TRAFFIC_AWARE"
    r = await http.post(URL, json=body, headers={"X-Goog-Api-Key": api_key, "X-Goog-FieldMask": FIELD_MASK}, timeout=15)
    if r.status_code != 200:
        log.warning("routes api failed: http=%s", r.status_code)
        raise DirectionsError(ERRORS.get(r.status_code, "MAPS_FAILED"))
    routes = r.json().get("routes") or []
    if not routes:
        raise DirectionsError("ROUTE_NOT_FOUND")
    return _route(routes[0])


def _route(route: dict[str, Any]) -> dict[str, Any]:
    coordinates = route.get("polyline", {}).get("geoJsonLinestring", {}).get("coordinates") or []
    path = [{"latitude": lat, "longitude": lng} for lng, lat, *_ in _thin(coordinates, MAX_PATH_POINTS)]
    legs = route.get("legs") or []
    end = (legs[-1].get("endLocation") or {}).get("latLng") if legs else None
    if not path or not end:
        raise DirectionsError("ROUTE_NOT_FOUND")
    steps = [
        {
            "instruction": (s.get("navigationInstruction") or {}).get("instructions", "")[:MAX_INSTRUCTION_CHARS],
            "distance_m": int(s.get("distanceMeters") or 0),
        }
        for leg in legs
        for s in leg.get("steps") or []
    ]
    return {
        "distance_m": int(route.get("distanceMeters") or 0),
        # Google writes durations as seconds with an "s": "754s".
        "duration_s": int(float(str(route.get("duration") or "0s").rstrip("s"))),
        "destination": {"latitude": end["latitude"], "longitude": end["longitude"]},
        "path": path,
        "steps": [s for s in steps if s["instruction"]][:MAX_STEPS],
    }


def _thin(points: list[Any], limit: int) -> list[Any]:
    """Every n-th point, keeping the last, so a long route stays drawable."""
    if len(points) <= limit:
        return points
    step = -(-len(points) // (limit - 1))
    return points[::step] + [points[-1]]
