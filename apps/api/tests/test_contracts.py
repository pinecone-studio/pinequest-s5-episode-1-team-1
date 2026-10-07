"""Pydantic models must accept every shared example and emit contract-valid JSON."""

from __future__ import annotations

import json

import pytest

from duud_api.config import get_settings
from duud_api.contracts import tool_manifest, validate_wire
from duud_api.models import ActionResultsRequest, ActionResultsResponse, AssistantContext, AssistantTurn
from duud_api.planner import function_specs

EXAMPLES = get_settings().contracts_dir / "examples"
MODELS = {
    "context": ("AssistantContext", AssistantContext),
    "turn": ("AssistantTurn", AssistantTurn),
    "results": ("ActionResultsRequest", ActionResultsRequest),
    "results-response": ("ActionResultsResponse", ActionResultsResponse),
}


@pytest.mark.parametrize("path", sorted(EXAMPLES.glob("*.json")), ids=lambda p: p.name)
def test_example_round_trips(path):
    schema_name, model = MODELS[path.name.split(".")[0]]
    parsed = model.model_validate(json.loads(path.read_text(encoding="utf-8")))
    assert validate_wire(schema_name, parsed.model_dump(mode="json")) == []


def test_every_tool_is_offered_to_the_llm():
    names = {f.name for f in function_specs()}
    assert set(tool_manifest()) <= names
    assert {"reply", "ask_clarification", "explain_limitation"} <= names


def test_confirm_tools_require_a_question():
    specs = {f.name: f for f in function_specs()}
    for tool in ("call_contact", "send_message"):
        assert "confirmation_question" in specs[tool].parameters["required"]
    assert "confirmation_question" not in specs["create_reminder"].parameters.get("properties", {})
