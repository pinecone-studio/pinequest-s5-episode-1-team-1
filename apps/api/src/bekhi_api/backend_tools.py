"""Tools whose executor is "backend". They run before the turn is returned."""

from __future__ import annotations

import logging
from datetime import date, datetime
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
    s = get_settings()
    place = UB
    name = (args.get("location_name") or "").strip()
    try:
        if name and name.lower() not in ("улаанбаатар", "ulaanbaatar", "уб", "ub"):
            r = await http.get(
                f"{s.open_meteo_geocoding_url}/v1/search", params={"name": name, "count": 1, "language": "mn"}
            )
            r.raise_for_status()
            hits = r.json().get("results") or []
            if not hits:
                return _fail(action_id, "get_weather", "LOCATION_NOT_FOUND")
            place = {"name": hits[0].get("name", name), "latitude": hits[0]["latitude"], "longitude": hits[0]["longitude"]}

        day = date.fromisoformat(args["date"]) if args.get("date") else client_now.date()
        r = await http.get(
            f"{s.open_meteo_base_url}/v1/forecast",
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
    except (httpx.HTTPError, KeyError, ValueError) as e:
        log.warning("weather lookup failed: %s", type(e).__name__)
        return _fail(action_id, "get_weather", "WEATHER_UNAVAILABLE")

    tmax = round(daily["temperature_2m_max"][0])
    tmin = round(daily["temperature_2m_min"][0])
    rain = daily.get("precipitation_probability_max", [None])[0]
    desc = _describe(daily["weather_code"][0])
    offset = (day - client_now.date()).days
    day_word = DAY_WORDS.get(offset, f"{day.month} сарын {day.day}-нд")
    verb = "байна" if offset == 0 else "байх төлөвтэй"
    summary = f"{day_word} {place['name']} орчимд {desc} {verb}. Өдөртөө {tmax}°, шөнөдөө {tmin}° хүрнэ."
    if rain is not None:
        summary += f" Хур тунадас орох магадлал {rain}%."
    return _ok(
        action_id,
        "get_weather",
        {"place": place["name"], "date": day.isoformat(), "temp_max_c": tmax, "temp_min_c": tmin,
         "precipitation_probability": rain, "summary_mn": summary},
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
