"""Dish ideas, recipes and places to eat (food.py), and how BEKHI says them."""

from __future__ import annotations

import json
from contextlib import ExitStack
from dataclasses import replace

import httpx
import pytest
from fastapi.testclient import TestClient

from bekhi_api import main as main_mod
from bekhi_api.compose import compose
from bekhi_api.config import get_settings
from bekhi_api.contracts import validate_wire
from bekhi_api.models import ActionRequest, ActionResult, Confirmation

from .conftest import context

ORIGIN = {"latitude": 47.9185, "longitude": 106.9176}
PLACES = [
    {
        "id": "far",
        "displayName": {"text": "Хаан хуушуур"},
        "location": {"latitude": 47.9198, "longitude": 106.9232},
        "shortFormattedAddress": "Энхтайваны өргөн чөлөө 12",
        "rating": 4.4,
        "userRatingCount": 210,
        "currentOpeningHours": {"openNow": True},
        "primaryTypeDisplayName": {"text": "Ресторан"},
    },
    {"id": "near", "displayName": {"text": "Мах Маркет"}, "location": {"latitude": 47.9179, "longitude": 106.9178}},
    {"id": "abroad", "displayName": {"text": "Эрээн хуушуур"}, "location": {"latitude": 43.65, "longitude": 111.97}},
    {"id": "nameless", "displayName": {"text": ""}, "location": {"latitude": 47.918, "longitude": 106.917}},
]
RECIPE = {
    "dish": "Цуйван",
    "servings": 4,
    "minutes": 50,
    "ingredients": ["500 г гурил", "400 г үхрийн мах", "1 лууван"],
    "steps": ["Гурилаа зуурч, нимгэн элдэнэ.", "Махаа хэрчиж шарна."],
}


def chat(client, text):
    r = client.post("/api/v1/assistant/chat", json={"text": text, "context": context()})
    assert r.status_code == 200, r.text
    return r.json()


def test_dish_ideas_ask_eat_in_or_out_without_another_model_step(client, planner):
    ideas = [{"dish": "Цуйван", "note": "хүйтэн өдөр дулаацуулна"}, {"dish": "Бууз"}, {"dish": "Гуляш"}]
    planner.then(("suggest_food", {"user_request": "Юу идэх вэ", "ideas": ideas}))

    turn = chat(client, "Юу идвэл дээр вэ?")
    assert planner.followups == []
    assert turn["stage"] == "final" and turn["intent"] == "suggest_food"
    assert turn["response"] == "Цуйван, бууз эсвэл гуляш идэж болох юм. Гэртээ хийх үү, гадуур идэх үү?"
    assert turn["actions"][0]["result"]["data"]["ideas"] == ideas


def test_recipe_is_shown_and_its_gist_said(client, planner):
    planner.then(("show_recipe", {"user_request": "Цуйван хийх арга", **RECIPE}))

    turn = chat(client, "Цуйван хийх арга хэлээч")
    data = turn["actions"][0]["result"]["data"]
    assert data["ingredients"] == RECIPE["ingredients"] and data["steps"] == RECIPE["steps"]
    assert turn["response"] == (
        "Цуйван: 4 хүнд, 50 минут орчим. Орц, хийх дарааллыг дэлгэц дээр харууллаа. Эхлээд: Гурилаа зуурч, нимгэн элдэнэ."
    )


def test_a_recipe_without_steps_is_not_shown(client, planner):
    planner.then(("show_recipe", {"user_request": "Цуйван", **RECIPE, "steps": []}))
    turn = chat(client, "Цуйван хийх арга")
    assert turn["intent"] == "error" and turn["actions"] == []


def test_restaurants_are_looked_up_on_the_phone(client, planner):
    planner.then(("find_restaurants", {"user_request": "Ойрхон хуушуур", "query": "хуушуур"}))
    turn = chat(client, "Ойролцоо хуушуур идэх газар байна уу?")
    assert turn["stage"] == "awaiting_device"
    assert turn["actions"][0]["arguments"] == {"query": "хуушуур"}


def say(tool, args, data):
    action = ActionRequest(id="a1", tool=tool, arguments=args, confirmation=Confirmation(required=False, prompt=None))
    result = ActionResult(action_id="a1", tool=tool, status="succeeded", executed_via="react_native", error_code=None, data=data)
    return compose([action], [result], "2026-10-06T12:00:00+08:00")


def test_restaurants_are_said_nearest_first():
    places = [
        {"name": "Хаан хуушуур", "distance_m": 248, "rating": 4.4, "open_now": False},
        {"name": "Мах Маркет", "distance_m": 432},
        {"name": "Зоог", "distance_m": 655},
        {"name": "Дөрөв дэх", "distance_m": 900},
    ]
    assert say("find_restaurants", {"query": "хуушуур"}, {"restaurants": places}) == (
        "Хамгийн ойрын хуушуур идэх газар Хаан хуушуур, 250 метрт. Үнэлгээ нь 4.4. Гэхдээ одоо хаалттай байна. "
        "Бас Мах Маркет 430 метр, Зоог 660 метр. Аль нэгийг нь дарвал зам заая."
    )
    assert say("find_restaurants", {}, {"restaurants": []}) == "Ойролцоо хоолны газар олдсонгүй."


@pytest.fixture
def places_client(monkeypatch):
    with ExitStack() as stack:

        def make(handler, key: str | None = "maps-key") -> TestClient:
            settings = replace(get_settings(), google_maps_api_key=key)
            monkeypatch.setattr(main_mod, "get_settings", lambda: settings)
            app = main_mod.create_app()
            c = stack.enter_context(TestClient(app))
            app.state.http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
            return c

        yield make


def test_nearby_restaurants_nearest_first_within_the_radius(places_client):
    sent: list[httpx.Request] = []

    def places(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json={"places": PLACES})

    r = places_client(places).post(
        "/api/v1/maps/restaurants/nearby", json={"origin": ORIGIN, "query": " хуушуур ", "radius_m": 1000}
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert validate_wire("RestaurantsResponse", body) == []
    assert [p["id"] for p in body["restaurants"]] == ["near", "far"]
    near, far = body["restaurants"]
    assert near["rating"] is None and near["open_now"] is None and near["address"] is None
    assert far["rating"] == 4.4 and far["rating_count"] == 210 and far["open_now"] is True
    assert far["address"] == "Энхтайваны өргөн чөлөө 12" and far["kind"] == "Ресторан"

    payload = json.loads(sent[0].content)
    assert payload["textQuery"] == "хуушуур" and payload["rankPreference"] == "DISTANCE"
    assert payload["locationBias"]["circle"] == {"center": ORIGIN, "radius": 1000.0}
    assert "places.rating" in sent[0].headers["X-Goog-FieldMask"]


def test_without_a_dish_any_place_to_eat(places_client):
    sent: list[httpx.Request] = []
    client = places_client(lambda request: sent.append(request) or httpx.Response(200, json={}))
    r = client.post("/api/v1/maps/restaurants/nearby", json={"origin": ORIGIN})
    assert r.status_code == 200 and r.json() == {"restaurants": []}
    assert json.loads(sent[0].content)["textQuery"] == "хоолны газар"


@pytest.mark.parametrize(("google", "message"), [(httpx.Response(403), "Places API"), (httpx.Response(500), "хоолны газр")])
def test_google_errors_become_mongolian(places_client, google, message):
    r = places_client(lambda request: google).post("/api/v1/maps/restaurants/nearby", json={"origin": ORIGIN})
    assert r.status_code == 502 and message in r.json()["error"]["message"]


def test_without_a_key_google_is_not_called(places_client):
    sent: list[httpx.Request] = []
    client = places_client(lambda request: sent.append(request) or httpx.Response(200), key=None)
    assert client.post("/api/v1/maps/restaurants/nearby", json={"origin": ORIGIN}).status_code == 503 and sent == []
