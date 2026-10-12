"""In-app directions from the Google Routes API (computeRoutes).

The key stays on this server: the app sends where the phone is and where the user wants to go,
and gets back the route to draw. Logs never contain either place.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
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
    "routes.legs.steps.staticDuration",
    "routes.legs.steps.navigationInstruction.instructions",
    "routes.legs.steps.transitDetails.headsign",
    "routes.legs.steps.transitDetails.stopCount",
    "routes.legs.steps.transitDetails.stopDetails",
    "routes.legs.steps.transitDetails.transitLine.name",
    "routes.legs.steps.transitDetails.transitLine.nameShort",
    "routes.legs.steps.transitDetails.transitLine.color",
    "routes.legs.steps.transitDetails.transitLine.textColor",
    "routes.legs.steps.transitDetails.transitLine.vehicle.type",
])
MAX_PATH_POINTS = 5000
MAX_STEPS = 200
MAX_INSTRUCTION_CHARS = 500
MAX_NAME_CHARS = 200
MAX_LINE_CHARS = 100
HEX_COLOR = re.compile(r"#[0-9a-fA-F]{6}")
# Google vehicle type -> what the app draws.
VEHICLES = {
    "BUS": "bus",
    "INTERCITY_BUS": "bus",
    "TROLLEYBUS": "trolleybus",
    "TRAM": "tram",
    "LIGHT_RAIL": "tram",
    "RAIL": "train",
    "HEAVY_RAIL": "train",
    "COMMUTER_TRAIN": "train",
    "HIGH_SPEED_TRAIN": "train",
    "LONG_DISTANCE_TRAIN": "train",
    "METRO_RAIL": "train",
    "SUBWAY": "train",
}

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
            "duration_s": _seconds(s.get("staticDuration")),
            "transit": _transit(s.get("transitDetails")),
        }
        for leg in legs
        for s in leg.get("steps") or []
    ]
    return {
        "distance_m": int(route.get("distanceMeters") or 0),
        "duration_s": _seconds(route.get("duration")),
        "destination": {"latitude": end["latitude"], "longitude": end["longitude"]},
        "path": path,
        "steps": [s for s in steps if s["instruction"] or s["transit"]][:MAX_STEPS],
    }


def _seconds(value: Any) -> int:
    """Google writes durations as seconds with an "s": "754s"."""
    try:
        return max(0, int(float(str(value or "0s").rstrip("s"))))
    except ValueError:
        return 0


def _transit(details: dict[str, Any] | None) -> dict[str, Any] | None:
    if not details:
        return None
    line = details.get("transitLine") or {}
    name = (line.get("nameShort") or line.get("name") or "").strip()[:MAX_LINE_CHARS]
    if not name:
        return None
    stops = details.get("stopDetails") or {}
    return {
        "vehicle": VEHICLES.get((line.get("vehicle") or {}).get("type", ""), "other"),
        "line": name,
        "color": _color(line.get("color")),
        "text_color": _color(line.get("textColor")),
        "headsign": (details.get("headsign") or "")[:MAX_NAME_CHARS] or None,
        "departure_stop": _stop(stops.get("departureStop")),
        "arrival_stop": _stop(stops.get("arrivalStop")),
        "stop_count": int(details.get("stopCount") or 0),
        "departure_time": _time(stops.get("departureTime")),
    }


def _stop(stop: dict[str, Any] | None) -> dict[str, Any]:
    stop = stop or {}
    at = (stop.get("location") or {}).get("latLng") or {}
    location = (
        {"latitude": at["latitude"], "longitude": at["longitude"]} if "latitude" in at and "longitude" in at else None
    )
    return {"name": (stop.get("name") or "")[:MAX_NAME_CHARS], "location": location}


def _color(value: Any) -> str | None:
    return value.upper() if isinstance(value, str) and HEX_COLOR.fullmatch(value) else None


def _time(value: Any) -> str | None:
    """RFC 3339 from Google ("2026-10-12T02:45:00Z") -> ISO 8601 with an offset, or None."""
    try:
        at = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return at.isoformat(timespec="seconds") if at.tzinfo else None


def _thin(points: list[Any], limit: int) -> list[Any]:
    """Every n-th point, keeping the last, so a long route stays drawable."""
    if len(points) <= limit:
        return points
    step = -(-len(points) // (limit - 1))
    return points[::step] + [points[-1]]
