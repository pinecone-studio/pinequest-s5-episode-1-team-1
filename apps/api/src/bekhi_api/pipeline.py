"""Text -> planned AssistantTurn, and device results -> final answer.

The backend decides WHAT should happen. It never performs iPhone actions and never
phrases a pending device action as done. Rules enforced here, in code:
- every tool argument is validated against the shared contract before it is sent
- calls and messages always carry a confirmation question
- free-text replies are dropped while device actions are pending
- the outgoing turn is validated against the contract JSON Schema
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, get_args
from uuid import UUID, uuid4

import httpx

from . import backend_tools, briefing, memory, todos
from .compose import FAILED_BY_CODE, compose
from .contracts import apply_defaults, tool_manifest, validate_tool_args, validate_wire
from .models import (
    ActionRequest,
    ActionResult,
    ActionResultsRequest,
    ActionResultsResponse,
    Alternative,
    AssistantContext,
    AssistantTurn,
    Clarification,
    Confirmation,
    Limitation,
    LimitationCode,
)
from .planner import BACKEND_FIELDS, CONFIRM_FIELD, SUMMARY_FIELD, function_specs, system_prompt
from .providers.base import FunctionCall, HistoryMessage, LLMPlanner, WebSearch
from .store import MemoryStore, PendingTurn

log = logging.getLogger(__name__)

MN_AI_FAILURE = "Уучлаарай, одоогоор ойлгоход асуудал гарлаа."
LIMITATION_CODES = set(get_args(LimitationCode))
ALTERNATIVE_KINDS = {"shortcut", "open_settings", "in_app"}
MAX_ACTIONS = 5
# Agent loop: after backend tools (search, weather, time) the model gets their results and
# continues, e.g. search -> search again -> answer. Device actions end the loop: their
# outcome only exists after the phone runs them.
MAX_AGENT_STEPS = 4


class ContractViolation(RuntimeError):
    pass


class UnknownTurn(LookupError):
    pass


@dataclass
class Deps:
    llm: LLMPlanner
    http: httpx.AsyncClient
    store: MemoryStore
    search: WebSearch | None = None
    todo_store: todos.TodoStore = field(default_factory=todos.FileTodoStore)
    memory_store: memory.FactStore = field(default_factory=memory.FileFactStore)
    # The sync account of the device asking (sync.account_key): whose to-do list it is.
    account: str | None = None


async def _run_backend_tool(action_id: str, tool: str, args: dict[str, Any], ctx: AssistantContext, deps: Deps) -> ActionResult:
    if tool == "get_weather":
        return await backend_tools.get_weather(action_id, args, ctx.client_now, deps.http)
    if tool == "get_current_time":
        return backend_tools.get_current_time(action_id, args, ctx.client_now)
    if tool == "daily_briefing":
        return await briefing.daily_briefing(action_id, args, ctx.client_now, deps.http, deps.todo_store, deps.account)
    if tool in TODO_TOOLS:
        try:
            return await _run_todo_tool(action_id, tool, args, ctx, deps)
        except httpx.HTTPError as e:
            log.warning("todo store failed: %s", type(e).__name__)
            return ActionResult(action_id=action_id, tool=tool, status="failed", executed_via="backend",
                                error_code="TODO_UNAVAILABLE", data=None)
    if tool in ("remember", "forget"):
        try:
            if tool == "remember":
                return await memory.remember(action_id, args, ctx.client_now, deps.memory_store, deps.account)
            return await memory.forget(action_id, args, deps.memory_store, deps.account)
        except httpx.HTTPError as e:
            log.warning("memory store failed: %s", type(e).__name__)
            return ActionResult(action_id=action_id, tool=tool, status="failed", executed_via="backend",
                                error_code="MEMORY_UNAVAILABLE", data=None)
    return await backend_tools.web_search(action_id, args, deps.search)


TODO_TOOLS = ("add_todo", "list_todos", "complete_todo", "delete_todo")


async def _run_todo_tool(action_id: str, tool: str, args: dict[str, Any], ctx: AssistantContext, deps: Deps) -> ActionResult:
    if tool == "add_todo":
        return await todos.add_todo(action_id, args, ctx.client_now, deps.todo_store, deps.account)
    if tool == "list_todos":
        return await todos.list_todos(action_id, args, ctx.client_now, deps.todo_store, deps.account)
    if tool == "complete_todo":
        return await todos.complete_todo(action_id, args, deps.todo_store, deps.account)
    return await todos.delete_todo(action_id, args, deps.todo_store, deps.account)


def _tool_response(result: ActionResult) -> dict[str, Any]:
    """What the model is told about a backend tool call it made."""
    if result.status == "succeeded":
        return result.data or {}
    code = result.error_code or "FAILED"
    # The reason in words, so the model does not suggest something that cannot help ("try again").
    return {"error": code, "reason": FAILED_BY_CODE.get(code, "")}


def _server_now() -> datetime:
    return datetime.now(timezone.utc)


def _fill_backend_fields(tool: str, args: dict[str, Any], ctx: AssistantContext) -> None:
    """A timer becomes the moment it rings, from this server's clock and in the user's offset,
    so every linked device rings together. An alarm or timer for all devices gets the id
    that every device's copy shares (sync.py)."""
    if tool == "set_timer":
        ends = _server_now() + timedelta(seconds=int(args["duration_seconds"]))
        args["fire_at"] = ends.astimezone(ctx.client_now.tzinfo).isoformat(timespec="seconds")
    if tool in BACKEND_FIELDS and args.get("target", "all") == "all":
        args["sync_id"] = str(uuid4())


def _fallback_confirmation(tool: str, args: dict[str, Any]) -> str:
    who = args.get("contact_name", "")
    return f"{who}: залгах уу?" if tool == "call_contact" else f"{who}: '{args.get('body', '')}' гэж явуулах уу?"


def _history_note(actions: list[ActionRequest]) -> str:
    """What the assistant planned, so follow-ups ("тэгээд 9 цагт") can reuse dates."""
    return "; ".join(f"[{a.tool} {json.dumps(a.arguments, ensure_ascii=False)}]" for a in actions)


async def plan_turn(text: str, ctx: AssistantContext, deps: Deps) -> AssistantTurn:
    conversation_id, conv = deps.store.get_or_create(ctx.conversation_id)
    manifest = tool_manifest()

    facts = await memory.facts_for(deps.memory_store, deps.account)
    calls = await deps.llm.plan(
        system=system_prompt(ctx.client_now, ctx.timezone, ctx.device.platform, facts),
        history=list(conv.history),
        user_text=text,
        functions=function_specs(),
    )

    actions: list[ActionRequest] = []
    replies: list[str] = []
    limitations: list[Limitation] = []
    clarification: Clarification | None = None
    summary: str | None = None
    invalid = False
    followed_up = False

    for step in range(MAX_AGENT_STEPS + 1):
        # The model must get an answer for every call it made, in order.
        results: list[tuple[FunctionCall, dict[str, Any]]] = []
        ran_backend_tool = False
        for call in calls:
            restated = str(call.args.pop(SUMMARY_FIELD, None) or "").strip()
            summary = summary or restated[:300] or None
            if call.name in manifest:
                if len(actions) >= MAX_ACTIONS:
                    results.append((call, {"error": "TOO_MANY_ACTIONS"}))
                    continue
                args = {k: v for k, v in call.args.items() if v is not None}
                question = args.pop(CONFIRM_FIELD, None)
                for name in BACKEND_FIELDS.get(call.name, ()):
                    args.pop(name, None)
                args = apply_defaults(call.name, args)
                errors = validate_tool_args(call.name, args)
                if call.name == "open_url" and not str(args.get("url", "")).lower().startswith(("http://", "https://")):
                    errors = ["url: only http(s) links are opened"]
                if errors:
                    # Log field paths only — never argument values (may contain personal data).
                    log.warning("invalid args for %s: %s", call.name, [e.split(":")[0] for e in errors])
                    invalid = True
                    results.append((call, {"error": "INVALID_ARGUMENTS"}))
                    continue
                _fill_backend_fields(call.name, args, ctx)
                entry = manifest[call.name]
                required = entry["confirmation"] == "always"
                prompt = None
                if required:
                    prompt = (str(question).strip() if question else "") or _fallback_confirmation(call.name, args)
                action = ActionRequest(
                    id=f"a{len(actions) + 1}",
                    tool=call.name,
                    arguments=args,
                    confirmation=Confirmation(required=required, prompt=prompt),
                )
                if entry["executor"] == "backend":
                    action.result = await _run_backend_tool(action.id, call.name, args, ctx, deps)
                    ran_backend_tool = True
                    results.append((call, _tool_response(action.result)))
                else:
                    results.append((call, {"status": "sent to the phone"}))
                actions.append(action)
                continue
            if call.name == "reply" and call.args.get("text"):
                replies.append(str(call.args["text"]).strip())
            elif call.name == "ask_clarification" and call.args.get("question"):
                clarification = Clarification(
                    question=str(call.args["question"]).strip(),
                    options=[str(o) for o in (call.args.get("options") or [])][:10],
                )
            elif call.name == "explain_limitation" and call.args.get("message"):
                kind = call.args.get("alternative_kind")
                kind = kind if kind in ALTERNATIVE_KINDS else "none"
                code = call.args.get("code")
                limitations.append(
                    Limitation(
                        code=code if code in LIMITATION_CODES else "other",
                        message=str(call.args["message"]).strip(),
                        alternative=Alternative(kind=kind, description=str(call.args.get("alternative_description") or "").strip())
                        if kind != "none"
                        else None,
                    )
                )
            else:
                log.warning("ignored function call %s", call.name)
            results.append((call, {"status": "shown to the user"}))

        device_pending = any(manifest[a.tool]["executor"] == "device" for a in actions)
        if not ran_backend_tool or device_pending or clarification is not None or invalid or step == MAX_AGENT_STEPS:
            break
        calls = await deps.llm.follow_up(results)
        followed_up = True

    now_iso = ctx.client_now.isoformat()
    device_pending = [a for a in actions if manifest[a.tool]["executor"] == "device"]
    to_confirm = [a for a in actions if a.confirmation.required]

    if invalid or (not actions and not replies and not limitations and clarification is None):
        # Never send a half-understood plan to the phone.
        actions, limitations, clarification, replies = [], [], None, []
        stage, response, intent = "final", MN_AI_FAILURE, "error"
    elif clarification is not None:
        actions = []
        stage, response, intent = "awaiting_clarification", clarification.question, "clarification"
    elif to_confirm:
        stage, response = "awaiting_confirmation", to_confirm[0].confirmation.prompt or ""
        intent = "multi" if len(actions) > 1 else actions[0].tool
    elif device_pending:
        stage, response = "awaiting_device", ""  # nothing is claimed before the phone reports back
        intent = "multi" if len(actions) > 1 else actions[0].tool
    else:
        parts = [
            f"{lim.message} {lim.alternative.description}".strip() if lim.alternative else lim.message
            for lim in limitations
        ]
        parts += replies
        # After the agent loop the model's reply already uses the tool results; do not repeat them.
        if actions and not (followed_up and replies):
            parts.append(compose(actions, [a.result for a in actions if a.result], now_iso))
        stage, response = "final", " ".join(p for p in parts if p)
        intent = "unsupported" if limitations and not actions else ("multi" if len(actions) > 1 else actions[0].tool if actions else "chitchat")

    turn = AssistantTurn(
        conversation_id=conversation_id,
        turn_id=uuid4(),
        transcript=text,
        summary=summary if intent != "error" else None,
        intent=intent,
        stage=stage,
        response=response[:1000],
        actions=actions,
        requires_confirmation=any(a.confirmation.required for a in actions),
        requires_clarification=clarification is not None,
        clarification=clarification,
        limitations=limitations,
        audio_url=None,
    )

    errors = validate_wire("AssistantTurn", turn.model_dump(mode="json"))
    if errors:
        log.error("outgoing turn violates contract: %s", errors)
        raise ContractViolation("turn does not match contract")

    conv.history.append(HistoryMessage("user", text))
    conv.history.append(HistoryMessage("assistant", response or _history_note(actions)))
    if stage in ("awaiting_confirmation", "awaiting_device"):
        notes = [lim.message for lim in limitations]
        conv.pending[turn.turn_id] = PendingTurn(actions=actions, now_iso=now_iso, notes=notes)
    return turn


def report_results(req: ActionResultsRequest, store: MemoryStore) -> ActionResultsResponse:
    conv = store.get(req.conversation_id)
    pending = conv.pending.pop(req.turn_id, None) if conv else None
    if conv is None or pending is None:
        raise UnknownTurn(str(req.turn_id))

    # Backend results are authoritative for backend tools; the device reports its own.
    backend_results = {a.id: a.result for a in pending.actions if a.result}
    results = [backend_results.get(r.action_id, r) for r in req.results]
    response = " ".join([compose(pending.actions, results, pending.now_iso), *pending.notes]).strip()[:1000]
    conv.history.append(HistoryMessage("assistant", response))
    return ActionResultsResponse(conversation_id=req.conversation_id, turn_id=req.turn_id, response=response, audio_url=None)
