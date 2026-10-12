"""Bus stops near the phone, from the Google Places API (New) Nearby Search.

Same key as directions; the Places API (New) must be enabled for it. Logs never contain the position.
"""

from __future__ import annotations

import logging
import math
from typing import Any

import httpx

from .directions import DirectionsError

log = logging.getLogger(__name__)

URL = "https://places.googleapis.com/v1/places:searchNearby"
FIELD_MASK = "places.id,places.displayName,places.location"
STOP_TYPES = ["bus_stop", "bus_station", "transit_station"]
# The most Nearby Search returns in one request.
MAX_STOPS = 20
MAX_NAME_CHARS = 200
ERRORS = {400: "MAPS_FAILED", 401: "PLACES_KEY_INVALID", 403: "PLACES_KEY_INVALID"}
EARTH_RADIUS_M = 6_371_000


async def nearby_stops(
    http: httpx.AsyncClient, api_key: str, origin: dict[str, float], radius_m: int
) -> list[dict[str, Any]]:
    body = {
        "includedTypes": STOP_TYPES,
        "maxResultCount": MAX_STOPS,
        "rankPreference": "DISTANCE",
        "locationRestriction": {"circle": {"center": origin, "radius": float(radius_m)}},
        "languageCode": "mn",
        "regionCode": "mn",
    }
    r = await http.post(URL, json=body, headers={"X-Goog-Api-Key": api_key, "X-Goog-FieldMask": FIELD_MASK}, timeout=10)
    if r.status_code != 200:
        log.warning("places api failed: http=%s", r.status_code)
        raise DirectionsError(ERRORS.get(r.status_code, "MAPS_FAILED"))
    stops = [s for s in (_stop(p, origin) for p in r.json().get("places") or []) if s]
    return sorted(stops, key=lambda s: s["distance_m"])


def _stop(place: dict[str, Any], origin: dict[str, float]) -> dict[str, Any] | None:
    at = place.get("location") or {}
    name = ((place.get("displayName") or {}).get("text") or "").strip()[:MAX_NAME_CHARS]
    if not place.get("id") or not name or "latitude" not in at or "longitude" not in at:
        return None
    location = {"latitude": at["latitude"], "longitude": at["longitude"]}
    return {"id": place["id"], "name": name, "location": location, "distance_m": round(distance_m(origin, location))}


def distance_m(a: dict[str, float], b: dict[str, float]) -> float:
    """Great-circle distance in metres."""
    lat1, lat2 = math.radians(a["latitude"]), math.radians(b["latitude"])
    d_lat = lat2 - lat1
    d_lng = math.radians(b["longitude"] - a["longitude"])
    h = math.sin(d_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(d_lng / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))
