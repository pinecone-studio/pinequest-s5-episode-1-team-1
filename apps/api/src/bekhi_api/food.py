"""Food: dish ideas and recipes, and places to eat near the phone.

suggest_food and show_recipe carry what the model wrote (validated against the contract); they
are returned as they are for the app's cards, with a short sentence to say. Restaurants come
from the Google Places API (New) Text Search, with the same key as directions and bus stops.
Logs never contain the position.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from .directions import DirectionsError
from .models import ActionResult
from .stops import ERRORS, distance_m

log = logging.getLogger(__name__)

URL = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = (
    "places.id,places.displayName,places.location,places.shortFormattedAddress,places.rating,"
    "places.userRatingCount,places.currentOpeningHours.openNow,places.primaryTypeDisplayName"
)
# Without a dish: any place to eat. "ресторан" alone misses cafes and canteens.
ANY_FOOD = "хоолны газар"
MAX_PLACES = 20
MAX_TEXT = 200


def _ok(action_id: str, tool: str, data: dict[str, Any]) -> ActionResult:
    return ActionResult(action_id=action_id, tool=tool, status="succeeded", executed_via="backend", error_code=None, data=data)


def _or_list(names: list[str]) -> str:
    """"Цуйван", "Цуйван эсвэл бууз", "Цуйван, бууз эсвэл гуляш"."""
    if len(names) == 1:
        return names[0]
    return f"{', '.join(names[:-1])} эсвэл {names[-1]}"


def suggest_food(action_id: str, args: dict[str, Any]) -> ActionResult:
    ideas = [{"dish": i["dish"], **({"note": i["note"]} if i.get("note") else {})} for i in args["ideas"]]
    dishes = [i["dish"] for i in ideas]
    dishes = [dishes[0], *(d[:1].lower() + d[1:] for d in dishes[1:])]
    summary = f"{_or_list(dishes)} идэж болох юм. Гэртээ хийх үү, гадуур идэх үү?"
    return _ok(action_id, "suggest_food", {"ideas": ideas, "summary_mn": summary})


def show_recipe(action_id: str, args: dict[str, Any]) -> ActionResult:
    steps = list(args["steps"])
    summary = (
        f"{args['dish']}: {args['servings']} хүнд, {_minutes_mn(int(args['minutes']))} орчим. "
        f"Орц, хийх дарааллыг дэлгэц дээр харууллаа. Эхлээд: {steps[0].rstrip('.')}."
    )
    return _ok(action_id, "show_recipe", {
        "dish": args["dish"],
        "servings": args["servings"],
        "minutes": args["minutes"],
        "ingredients": list(args["ingredients"]),
        "steps": steps,
        "summary_mn": summary,
    })


def _minutes_mn(minutes: int) -> str:
    """45 -> "45 минут", 90 -> "1 цаг 30 минут", 120 -> "2 цаг"."""
    h, m = divmod(minutes, 60)
    return " ".join(p for p in (f"{h} цаг" if h else "", f"{m} минут" if m else "") if p)


async def nearby_restaurants(
    http: httpx.AsyncClient, api_key: str, origin: dict[str, float], query: str | None, radius_m: int
) -> list[dict[str, Any]]:
    body = {
        "textQuery": query or ANY_FOOD,
        "pageSize": MAX_PLACES,
        "rankPreference": "DISTANCE",
        "locationBias": {"circle": {"center": origin, "radius": float(radius_m)}},
        "languageCode": "mn",
        "regionCode": "mn",
    }
    r = await http.post(URL, json=body, headers={"X-Goog-Api-Key": api_key, "X-Goog-FieldMask": FIELD_MASK}, timeout=10)
    if r.status_code != 200:
        log.warning("places text search failed: http=%s", r.status_code)
        raise DirectionsError(ERRORS.get(r.status_code, "MAPS_FAILED"))
    # The bias only prefers the circle: places further away are left out.
    places = [p for p in (_place(p, origin) for p in r.json().get("places") or []) if p and p["distance_m"] <= radius_m]
    return sorted(places, key=lambda p: p["distance_m"])


def _place(place: dict[str, Any], origin: dict[str, float]) -> dict[str, Any] | None:
    at = place.get("location") or {}
    name = _text(place.get("displayName"))
    if not place.get("id") or not name or "latitude" not in at or "longitude" not in at:
        return None
    location = {"latitude": at["latitude"], "longitude": at["longitude"]}
    rating = place.get("rating")
    count = place.get("userRatingCount")
    open_now = (place.get("currentOpeningHours") or {}).get("openNow")
    return {
        "id": place["id"],
        "name": name,
        "location": location,
        "distance_m": round(distance_m(origin, location)),
        "address": (str(place.get("shortFormattedAddress") or "").strip()[:MAX_TEXT]) or None,
        "rating": float(rating) if isinstance(rating, (int, float)) and 0 <= rating <= 5 else None,
        "rating_count": count if isinstance(count, int) and count >= 0 else None,
        "open_now": open_now if isinstance(open_now, bool) else None,
        "kind": _text(place.get("primaryTypeDisplayName"))[:100] or None,
    }


def _text(localized: Any) -> str:
    return str((localized or {}).get("text") or "").strip()[:MAX_TEXT] if isinstance(localized, dict) else ""
