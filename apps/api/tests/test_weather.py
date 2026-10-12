"""The weather when Open-Meteo is busy: a cloud host's shared address often gets 429 from it. Then MET
Norway gives the forecast and Nominatim finds the place. All services are faked."""

from __future__ import annotations

from datetime import datetime

import httpx

from bekhi_api import backend_tools

NOW = datetime.fromisoformat("2026-10-12T09:00:00+08:00")


def met_forecast(request: httpx.Request) -> httpx.Response:
    """Tomorrow in Ulaanbaatar (UTC+8), hourly: -3° at dawn, 8° in the afternoon, cloudy at noon."""
    steps = []
    for utc_hour, temp, symbol in [(16, -2.0, "clearsky_night"), (22, -3.4, "fair_day"), (4, 6.0, "cloudy"),
                                   (7, 8.3, "partlycloudy_day"), (13, 1.0, "clearsky_night")]:
        day = "2026-10-12" if utc_hour >= 16 else "2026-10-13"
        steps.append({"time": f"{day}T{utc_hour:02d}:00:00Z", "data": {
            "instant": {"details": {"air_temperature": temp}},
            "next_1_hours": {"summary": {"symbol_code": symbol}}}})
    return httpx.Response(200, json={"properties": {"timeseries": steps}})


class Busy:
    """Open-Meteo answering 429; MET Norway and Nominatim answering."""

    def __init__(self) -> None:
        self.asked: list[str] = []
        self.agents: set[str] = set()

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.asked.append(request.url.host)
        if "open-meteo" in request.url.host:
            return httpx.Response(429, json={"reason": "Too many requests"})
        self.agents.add(request.headers.get("user-agent", ""))
        if request.url.host == "api.met.no":
            return met_forecast(request)
        return httpx.Response(200, json=[{"lat": "49.48", "lon": "105.96", "display_name": "Дархан"}])


async def test_met_norway_answers_when_open_meteo_is_busy():
    fake = Busy()
    async with httpx.AsyncClient(transport=httpx.MockTransport(fake)) as http:
        r = await backend_tools.get_weather("w", {"date": "2026-10-13"}, NOW, http)
    assert r.status == "succeeded"
    assert (r.data["temp_max_c"], r.data["temp_min_c"], r.data["weather_code"]) == (8, -3, 3)  # the sky nearest noon
    assert r.data["condition"] == "үүлэрхэг" and r.data["precipitation_probability"] is None
    assert "Хур тунадас" not in r.data["summary_mn"]  # MET Norway's compact forecast has no chance of rain
    assert fake.asked == ["api.open-meteo.com", "api.met.no"]
    assert all(agent.startswith("BEKHI/") for agent in fake.agents)  # MET Norway asks who is calling


async def test_nominatim_finds_the_place_when_open_meteo_is_busy():
    fake = Busy()
    async with httpx.AsyncClient(transport=httpx.MockTransport(fake)) as http:
        r = await backend_tools.get_weather("w", {"location_name": "Дархан", "date": "2026-10-13"}, NOW, http)
    assert r.status == "succeeded" and r.data["place"] == "Дархан"
    assert "nominatim.openstreetmap.org" in fake.asked


async def test_a_place_and_its_forecast_are_asked_once_in_a_while():
    fake = Busy()
    async with httpx.AsyncClient(transport=httpx.MockTransport(fake)) as http:
        for _ in range(3):
            await backend_tools.get_weather("w", {"location_name": "Дархан", "date": "2026-10-13"}, NOW, http)
    assert len(fake.asked) == 4  # geocoding and forecast, each Open-Meteo then the other service: once


async def test_other_errors_do_not_hide_behind_the_other_service():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(400))) as http:
        r = await backend_tools.get_weather("w", {"date": "2026-10-13"}, NOW, http)
    assert r.error_code == "WEATHER_UNAVAILABLE"
