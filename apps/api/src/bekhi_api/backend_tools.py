"""Tools whose executor is "backend". They run before the turn is returned."""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, tzinfo
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from .config import get_settings
from .models import ActionResult
from .providers.base import SearchError

log = logging.getLogger(__name__)

UB = {"name": "Улаанбаатар", "latitude": 47.9077, "longitude": 106.8832}

# WMO weather codes -> Mongolian adjective phrase
WMO_MN: list[tuple[range | tuple[int, ...], str]] = [
    ((0,), "цэлмэг"),
    ((1, 2), "багавтар үүлтэй"),
    ((3,), "үүлэрхэг"),
    ((45, 48), "манантай"),
    (range(51, 58), "шиврээ бороотой"),
    (range(61, 68), "бороотой"),
    (range(71, 78), "цастай"),
    (range(80, 83), "аадар бороотой"),
    ((85, 86), "цас орох"),
    (range(95, 100), "аянга цахилгаантай бороотой"),
]

DAY_WORDS = {0: "Өнөөдөр", 1: "Маргааш", 2: "Нөгөөдөр"}

# Open-Meteo limits each IP address, and a cloud host's address is shared with many other apps, so it
# often answers 429 there. Then MET Norway (the Norwegian weather service: free, worldwide, no key,
# asks for a User-Agent) gives the forecast, and OpenStreetMap's Nominatim finds the place.
MET_URL = "https://api.met.no/weatherapi/locationforecast/2.0/compact"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "BEKHI/0.1 (Mongolian voice assistant; github.com/pinecone-studio/pinequest-s5-episode-1-team-1)"
# MET Norway's symbols (without _day / _night) -> WMO codes, as Open-Meteo gives them.
MET_CODES = {
    "clearsky": 0, "fair": 1, "partlycloudy": 2, "cloudy": 3, "fog": 45,
    "lightrain": 61, "rain": 63, "heavyrain": 65, "lightsleet": 66, "sleet": 67, "heavysleet": 67,
    "lightrainshowers": 80, "rainshowers": 81, "heavyrainshowers": 82,
    "lightsleetshowers": 66, "sleetshowers": 67, "heavysleetshowers": 67,
    "lightsnow": 71, "snow": 73, "heavysnow": 75, "lightsnowshowers": 85, "snowshowers": 85, "heavysnowshowers": 86,
}
CACHE_SECONDS = 1800  # a place's forecast for a day, and where a place is, asked again within this
_cache: dict[tuple[Any, ...], tuple[float, Any]] = {}


def clear_cache() -> None:
    _cache.clear()


def _cached(key: tuple[Any, ...]) -> Any:
    hit = _cache.get(key)
    return hit[1] if hit and hit[0] > time.monotonic() else None


def _keep(key: tuple[Any, ...], value: Any) -> Any:
    _cache[key] = (time.monotonic() + CACHE_SECONDS, value)
    return value


def _busy(e: Exception) -> bool:
    """Worth asking the other service: rate limited, down, or unreachable."""
    if isinstance(e, httpx.HTTPStatusError):
        return e.response.status_code == 429 or e.response.status_code >= 500
    return isinstance(e, httpx.TransportError)


async def _geocode(http: httpx.AsyncClient, name: str) -> dict[str, Any] | None:
    key = ("place", name.casefold())
    if (hit := _cached(key)) is not None:
        return hit
    try:
        r = await http.get(f"{get_settings().open_meteo_geocoding_url}/v1/search",
                           params={"name": name, "count": 1, "language": "mn"})
        r.raise_for_status()
        hits = r.json().get("results") or []
        place = {"name": hits[0].get("name", name), "latitude": hits[0]["latitude"],
                 "longitude": hits[0]["longitude"]} if hits else None
    except httpx.HTTPError as e:
        if not _busy(e):
            raise
        log.warning("open-meteo geocoding busy (%s): asking nominatim", type(e).__name__)
        r = await http.get(NOMINATIM_URL, params={"q": name, "format": "json", "limit": 1, "accept-language": "mn"},
                           headers={"User-Agent": USER_AGENT})
        r.raise_for_status()
        hits = r.json()
        place = {"name": name, "latitude": float(hits[0]["lat"]), "longitude": float(hits[0]["lon"])} if hits else None
    return _keep(key, place) if place else None


async def _open_meteo(http: httpx.AsyncClient, place: dict[str, Any], day: date) -> dict[str, Any]:
    r = await http.get(
        f"{get_settings().open_meteo_base_url}/v1/forecast",
        params={
            "latitude": place["latitude"],
            "longitude": place["longitude"],
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            "timezone": "auto",
            "start_date": day.isoformat(),
            "end_date": day.isoformat(),
        },
    )
    r.raise_for_status()
    daily = r.json()["daily"]
    return {"max": daily["temperature_2m_max"][0], "min": daily["temperature_2m_min"][0],
            "rain": daily.get("precipitation_probability_max", [None])[0], "code": daily["weather_code"][0]}


async def _met_norway(http: httpx.AsyncClient, place: dict[str, Any], day: date, tz: tzinfo) -> dict[str, Any]:
    """The day's highest and lowest temperature and its midday sky, from the hourly forecast."""
    r = await http.get(MET_URL, params={"lat": round(place["latitude"], 4), "lon": round(place["longitude"], 4)},
                       headers={"User-Agent": USER_AGENT})
    r.raise_for_status()
    temps: list[float] = []
    sky: tuple[float, str] | None = None  # (hours from noon, symbol)
    for step in r.json()["properties"]["timeseries"]:
        local = datetime.fromisoformat(step["time"].replace("Z", "+00:00")).astimezone(tz)
        if local.date() != day:
            continue
        data = step["data"]
        temps.append(data["instant"]["details"]["air_temperature"])
        nxt = data.get("next_1_hours") or data.get("next_6_hours") or data.get("next_12_hours")
        if nxt and (sky is None or abs(local.hour - 12) < sky[0]):
            sky = (abs(local.hour - 12), nxt["summary"]["symbol_code"].split("_")[0])
    if not temps:
        raise ValueError("no forecast for that day")
    symbol = sky[1] if sky else ""
    return {"max": max(temps), "min": min(temps), "rain": None,
            "code": 95 if "thunder" in symbol else MET_CODES.get(symbol)}


async def _forecast(http: httpx.AsyncClient, place: dict[str, Any], day: date, tz: tzinfo) -> dict[str, Any]:
    key = ("forecast", round(place["latitude"], 2), round(place["longitude"], 2), day.isoformat())
    if (hit := _cached(key)) is not None:
        return hit
    try:
        forecast = await _open_meteo(http, place, day)
    except httpx.HTTPError as e:
        if not _busy(e):
            raise
        log.warning("open-meteo busy (%s): asking met norway", type(e).__name__)
        forecast = await _met_norway(http, place, day, tz)
    return _keep(key, forecast)


def _describe(code: int | None) -> str:
    for codes, text in WMO_MN:
        if code in codes:
            return text
    return "тодорхойгүй"


def _ok(action_id: str, tool: str, data: dict[str, Any]) -> ActionResult:
    return ActionResult(action_id=action_id, tool=tool, status="succeeded", executed_via="backend", error_code=None, data=data)


def _fail(action_id: str, tool: str, code: str) -> ActionResult:
    return ActionResult(action_id=action_id, tool=tool, status="failed", executed_via="backend", error_code=code, data=None)


async def get_weather(action_id: str, args: dict[str, Any], client_now: datetime, http: httpx.AsyncClient) -> ActionResult:
    place: dict[str, Any] | None = UB
    name = (args.get("location_name") or "").strip()
    try:
        if name and name.lower() not in ("улаанбаатар", "ulaanbaatar", "уб", "ub"):
            place = await _geocode(http, name)
            if place is None:
                return _fail(action_id, "get_weather", "LOCATION_NOT_FOUND")
        day = date.fromisoformat(args["date"]) if args.get("date") else client_now.date()
        forecast = await _forecast(http, place, day, client_now.tzinfo or ZoneInfo("Asia/Ulaanbaatar"))
    except (httpx.HTTPError, KeyError, ValueError, IndexError) as e:
        log.warning("weather lookup failed: %s", type(e).__name__)
        return _fail(action_id, "get_weather", "WEATHER_UNAVAILABLE")

    tmax = round(forecast["max"])
    tmin = round(forecast["min"])
    rain = forecast["rain"]
    code = forecast["code"]
    desc = _describe(code)
    offset = (day - client_now.date()).days
    day_word = DAY_WORDS.get(offset, f"{day.month} сарын {day.day}-нд")
    verb = "байна" if offset == 0 else "байх төлөвтэй"
    summary = f"{day_word} {place['name']} орчимд {desc} {verb}. Өдөртөө {tmax}°, шөнөдөө {tmin}° хүрнэ."
    if rain is not None:
        summary += f" Хур тунадас орох магадлал {rain}%."
    return _ok(
        action_id,
        "get_weather",
        # weather_code and condition: the app draws the day's weather (WMO code) as a card.
        {"place": place["name"], "date": day.isoformat(), "temp_max_c": tmax, "temp_min_c": tmin,
         "precipitation_probability": rain, "weather_code": code, "condition": desc, "summary_mn": summary},
    )


def get_current_time(action_id: str, args: dict[str, Any], client_now: datetime) -> ActionResult:
    tz_name = args.get("timezone")
    try:
        now = datetime.now(ZoneInfo(tz_name)) if tz_name else datetime.now(client_now.tzinfo)
    except Exception:
        now = datetime.now(client_now.tzinfo)
    return _ok(action_id, "get_current_time", {"time": now.strftime("%H:%M"), "summary_mn": f"Одоо {now:%H:%M} болж байна."})


async def web_search(action_id: str, args: dict[str, Any], searcher: Any | None) -> ActionResult:
    if searcher is None:
        return _fail(action_id, "web_search", "WEB_SEARCH_NOT_CONFIGURED")
    try:
        found = await searcher.search(args["query"])
    except SearchError as e:
        return _fail(action_id, "web_search", e.code)
    except Exception as e:
        log.warning("web search failed: %s", type(e).__name__)
        return _fail(action_id, "web_search", "WEB_SEARCH_FAILED")
    if not found.get("answer"):
        return _fail(action_id, "web_search", "WEB_SEARCH_FAILED")
    return _ok(action_id, "web_search", {**found, "summary_mn": found["answer"]})
