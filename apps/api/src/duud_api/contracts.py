"""Loads the shared contract (packages/contracts/generated) and validates against it.

The zod definitions in packages/contracts are the source of truth. The backend
validates every outgoing turn and every tool argument against the exported
JSON Schema, so it can never send the phone a malformed action.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from .config import get_settings


@lru_cache
def _load(name: str) -> dict[str, Any]:
    path = get_settings().contracts_dir / "generated" / name
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache
def tool_manifest() -> dict[str, dict[str, Any]]:
    return {t["name"]: t for t in _load("tools.manifest.json")["tools"]}


@lru_cache
def _validator(schema_json: str) -> Draft202012Validator:
    return Draft202012Validator(json.loads(schema_json), format_checker=FormatChecker())


def _validate(schema: dict[str, Any], value: Any) -> list[str]:
    v = _validator(json.dumps(schema, sort_keys=True))
    return [f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}" for e in v.iter_errors(value)]


def validate_tool_args(tool: str, args: dict[str, Any]) -> list[str]:
    manifest = tool_manifest()
    if tool not in manifest:
        return [f"unknown tool {tool}"]
    return _validate(manifest[tool]["parameters"], args)


def apply_defaults(tool: str, args: dict[str, Any]) -> dict[str, Any]:
    """Fill top-level schema defaults (e.g. open_maps.mode = "driving")."""
    props = tool_manifest()[tool]["parameters"].get("properties", {})
    out = dict(args)
    for key, spec in props.items():
        if key not in out and "default" in spec:
            out[key] = spec["default"]
    return out


def validate_wire(schema_name: str, value: Any) -> list[str]:
    return _validate(_load("wire.schema.json")["schemas"][schema_name], value)
