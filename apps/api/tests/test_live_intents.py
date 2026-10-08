"""Runs packages/contracts/fixtures/intent-cases.json through the REAL Gemini planner.

    uv run pytest -m live -v

Needs GEMINI_API_KEY in apps/api/.env. Costs a few cents per run.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from bekhi_api import main as main_mod
from bekhi_api.config import get_settings

from .conftest import context, open_meteo

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not get_settings().gemini_api_key, reason="GEMINI_API_KEY not set"),
]

FIXTURES = json.loads((get_settings().contracts_dir / "fixtures" / "intent-cases.json").read_text(encoding="utf-8"))


def _ctx(conversation_id: str | None = None) -> dict[str, Any]:
    ctx = context(conversation_id)
    ctx["client_now"] = FIXTURES["reference_now"]
    return ctx


@pytest.fixture(scope="module")
def live_client():
    with TestClient(main_mod.app) as c:
        main_mod.app.state.http = httpx.AsyncClient(transport=httpx.MockTransport(open_meteo))
        yield c


def _check(turn: dict[str, Any], expected: dict[str, Any], utterance: str) -> None:
    tools = [a["tool"] for a in turn["actions"]]
    assert tools == expected["tools"], f"{utterance!r}: got {tools}, response={turn['response']!r}"
    for i, args in enumerate(expected.get("arguments", [])):
        for k, v in args.items():
            assert turn["actions"][i]["arguments"].get(k) == v, f"{utterance!r}: {k}"
    for i, contains in enumerate(expected.get("argument_contains", [])):
        for k, v in contains.items():
            assert v in str(turn["actions"][i]["arguments"].get(k, "")).lower(), f"{utterance!r}: {k} lacks {v!r}"
    if "requires_confirmation" in expected:
        assert turn["requires_confirmation"] is expected["requires_confirmation"], utterance
    if "limitation" in expected:
        assert [lim["code"] for lim in turn["limitations"]] == [expected["limitation"]], utterance


CASES = [(c["id"], u, c["expected"]) for c in FIXTURES["cases"] for u in [c["utterance"], *c.get("variants", [])]]


@pytest.mark.parametrize(("case_id", "utterance", "expected"), CASES, ids=[f"{c[0]}:{c[1]}" for c in CASES])
def test_intent(live_client, case_id, utterance, expected):
    r = live_client.post("/api/v1/assistant/chat", json={"text": utterance, "context": _ctx()})
    assert r.status_code == 200, r.text
    _check(r.json(), expected, utterance)


@pytest.mark.parametrize("conv", FIXTURES["conversations"], ids=lambda c: c["id"])
def test_conversation(live_client, conv):
    conversation_id = None
    for turn_spec in conv["turns"]:
        r = live_client.post(
            "/api/v1/assistant/chat", json={"text": turn_spec["utterance"], "context": _ctx(conversation_id)}
        )
        assert r.status_code == 200, r.text
        turn = r.json()
        conversation_id = turn["conversation_id"]
        _check(turn, turn_spec["expected"], turn_spec["utterance"])
