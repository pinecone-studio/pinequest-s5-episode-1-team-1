"""What BEKHI says after the phone opened a route or looked for bus stops."""

from __future__ import annotations

from typing import Any

import pytest

from bekhi_api.compose import sentence_for
from bekhi_api.models import ActionRequest, ActionResult

NOW = "2026-10-12T11:00:00+08:00"


def say(tool: str, arguments: dict[str, Any], status: str, data: dict | None = None, error_code: str | None = None) -> str:
    action = ActionRequest(id="a1", tool=tool, arguments=arguments, confirmation={"required": False})
    result = ActionResult(
        action_id="a1", tool=tool, status=status, executed_via="react_native", error_code=error_code, data=data
    )
    return sentence_for(action, result, NOW)


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("transit", "За, Зайсан руу автобусаар очих замыг газрын зураг дээр нээлээ."),
        ("walking", "За, Зайсан руу алхаж очих замыг газрын зураг дээр нээлээ."),
        ("driving", "За, Зайсан руу замыг газрын зураг дээр нээлээ."),
    ],
)
def test_the_route_sentence_names_how(mode, expected):
    assert say("open_maps", {"destination": "Зайсан", "mode": mode}, "handed_off") == expected


def test_nearest_stops_are_read_out():
    stops = [
        {"name": "Сүхбаатарын талбайн төв зогсоол", "distance_m": 72},
        {"name": "Цэцэг төв", "distance_m": 425},
        {"name": "МУБИС", "distance_m": 446},
        {"name": "Төв номын сан", "distance_m": 480},
    ]
    assert say("find_bus_stops", {}, "succeeded", {"stops": stops}) == (
        "Хамгийн ойрын буудал Сүхбаатарын талбайн төв зогсоол, 70 метрийн зайтай. "
        "Дараа нь Цэцэг төв 430 метр, МУБИС 450 метр. Газрын зураг дээр харууллаа."
    )


def test_no_stops_nearby():
    assert say("find_bus_stops", {}, "succeeded", {"stops": []}) == "Ойролцоо автобусны буудал олдсонгүй."


def test_location_refused():
    assert "байршлын зөвшөөрөл" in say("find_bus_stops", {}, "permission_denied", error_code="LOCATION_DENIED")
