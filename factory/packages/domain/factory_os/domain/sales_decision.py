"""SalesDecision: conversational proposal from the LLM seller (ADR-003).

Runtime validates and executes. Never grants permissions or invents facts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from factory_os.contracts.skills import ADRI_SKILLS
from factory_os.domain.models import NextAction, WorkingState
from factory_os.domain.response_goals import normalize_response_goal

ADRI_SKILL_NAMES = frozenset(skill.name for skill in ADRI_SKILLS)
ADRI_READ_TOOLS = frozenset({"catalog.search", "send_product_image"})
ADRI_WRITE_TOOLS = frozenset({"cart.add", "cart.remove", "order.create"})
ADRI_TOOLS = ADRI_READ_TOOLS | ADRI_WRITE_TOOLS

_ACTION_ALIASES = {
    "search": NextAction.SEARCH_CATALOG,
    "greet": NextAction.ANSWER,
    "close": NextAction.CREATE_ORDER,
}
_ACTIONS = {item.value: item for item in NextAction}
_ACTIONS.update(_ACTION_ALIASES)
_SKILLS = {
    NextAction.ANSWER: "customer_assistance",
    NextAction.ASK_DISCOVERY_QUESTION: "sales_discovery",
    NextAction.SEARCH_CATALOG: "product_recommendation",
    NextAction.RECOMMEND: "product_recommendation",
    NextAction.COMPARE: "product_recommendation",
    NextAction.HANDLE_OBJECTION: "objection_handling",
    NextAction.REQUEST_CONFIRMATION: "sales_closing",
    NextAction.CREATE_ORDER: "sales_closing",
    NextAction.ADD_TO_CART: "sales_closing",
    NextAction.HANDOFF: "sales_closing",
    NextAction.ESCALATE: "customer_assistance",
}
_TOOL_ACTIONS = {
    "catalog.search": NextAction.SEARCH_CATALOG,
    "cart.add": NextAction.ADD_TO_CART,
    "cart.remove": NextAction.ADD_TO_CART,
    "order.create": NextAction.CREATE_ORDER,
    "payment.create_qr": NextAction.ANSWER,
    "send_product_image": NextAction.RECOMMEND,
}


@dataclass(frozen=True)
class PreferencePatch:
    """Observed customer preferences for this turn.

    durable=True only when the customer stated them explicitly.
    Inferences stay turn-local and must not become durable facts.
    """

    budget_max: Decimal | None = None
    size: str | None = None
    color: str | None = None
    occasion: str | None = None
    style: str | None = None
    durable: bool = False

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"durable": self.durable}
        if self.budget_max is not None:
            out["budget_max"] = str(self.budget_max)
        for key in ("size", "color", "occasion", "style"):
            value = getattr(self, key)
            if value:
                out[key] = value
        return out

    def is_empty(self) -> bool:
        return (
            self.budget_max is None
            and not self.size
            and not self.color
            and not self.occasion
            and not self.style
        )


@dataclass(frozen=True)
class SalesDecision:
    """Structured seller proposal for one turn."""

    action: NextAction
    skill: str
    understanding: str = ""
    preference_patch: PreferencePatch = field(default_factory=PreferencePatch)
    tool_call: dict[str, Any] | None = None
    response_goal: str = ""
    provider: str = "unknown"
    tone: str = "cordial"

    def arguments(self) -> dict[str, Any]:
        """Flatten tool_call into the legacy ActionProposal.arguments shape."""
        args: dict[str, Any] = {}
        if self.tool_call:
            name = str(self.tool_call.get("name") or "").strip()
            raw_args = self.tool_call.get("arguments")
            if isinstance(raw_args, dict):
                args.update(raw_args)
            if name:
                args["tool"] = name
        return args


def _parse_budget(raw: object) -> Decimal | None:
    if raw is None or raw == "":
        return None
    try:
        value = Decimal(str(raw).replace(",", ".").strip())
    except (InvalidOperation, ValueError):
        return None
    if value <= 0:
        return None
    return value


def _parse_preference_patch(raw: object) -> PreferencePatch:
    if not isinstance(raw, dict):
        return PreferencePatch()
    size = str(raw.get("size") or "").strip() or None
    color = str(raw.get("color") or "").strip() or None
    occasion = str(raw.get("occasion") or "").strip() or None
    style = str(raw.get("style") or "").strip() or None
    durable = bool(raw.get("durable", False))
    # Explicit customer fields may arrive without durable flag — treat non-empty as durable.
    if any((size, color, occasion, style, raw.get("budget_max") is not None)) and "durable" not in raw:
        durable = True
    return PreferencePatch(
        budget_max=_parse_budget(raw.get("budget_max")),
        size=size,
        color=color,
        occasion=occasion,
        style=style,
        durable=durable,
    )


def _parse_tool_call(payload: dict[str, Any]) -> dict[str, Any] | None:
    raw = payload.get("tool_call")
    if isinstance(raw, dict):
        name = str(raw.get("name") or "").strip()
        arguments = raw.get("arguments") if isinstance(raw.get("arguments"), dict) else {}
        if name:
            return {"name": name, "arguments": dict(arguments)}
    # Legacy flat shape: tool + arguments
    tool = str(payload.get("tool") or "").strip()
    arguments = dict(payload.get("arguments") or {}) if isinstance(payload.get("arguments"), dict) else {}
    if tool:
        return {"name": tool, "arguments": arguments}
    if arguments.get("query") or arguments.get("codigo") or arguments.get("variant_sku"):
        # Infer catalog.search when query present without tool name
        if arguments.get("query"):
            return {"name": "catalog.search", "arguments": arguments}
        return {"name": "", "arguments": arguments}
    return None


def parse_sales_decision(payload: dict[str, Any], *, provider: str) -> SalesDecision | None:
    """Build a SalesDecision from a model JSON object. Returns None if action invalid."""
    from factory_os.domain.seed import normalize

    tool_call = _parse_tool_call(payload)
    tool_name = str((tool_call or {}).get("name") or "").strip()
    action = _ACTIONS.get(normalize(str(payload.get("action") or "")))
    if action is None and tool_name:
        action = _TOOL_ACTIONS.get(tool_name)
    if action is None:
        return None
    skill = _SKILLS.get(action) or "customer_assistance"
    return SalesDecision(
        action=action,
        skill=skill,
        understanding=str(payload.get("understanding") or "").strip()[:500],
        preference_patch=_parse_preference_patch(payload.get("preference_patch")),
        tool_call=tool_call,
        response_goal=normalize_response_goal(str(payload.get("response_goal") or "")),
        provider=provider,
        tone=str(payload.get("tone") or "cordial"),
    )


def validate_sales_decision(decision: SalesDecision) -> list[str]:
    """Return validation errors (empty = ok). Does not execute tools."""
    errors: list[str] = []
    if decision.action not in NextAction:
        errors.append(f"unknown action {decision.action}")
    if decision.skill not in ADRI_SKILL_NAMES:
        errors.append(f"unknown skill {decision.skill}")
    if decision.tool_call:
        name = str(decision.tool_call.get("name") or "").strip()
        if name and name not in ADRI_TOOLS:
            errors.append(f"tool not allowed for Adri: {name}")
        if name == "cart.add" and decision.action not in {
            NextAction.ADD_TO_CART,
            NextAction.CREATE_ORDER,
            NextAction.REQUEST_CONFIRMATION,
        }:
            errors.append(f"write tool {name} requires add_to_cart")
        elif name == "order.create" and decision.action not in {
            NextAction.CREATE_ORDER,
            NextAction.REQUEST_CONFIRMATION,
        }:
            errors.append(f"write tool {name} requires create_order/request_confirmation")
        elif name == "cart.remove" and decision.action is not NextAction.ADD_TO_CART:
            errors.append(f"write tool {name} requires add_to_cart")
    return errors


def apply_preference_patch(state: WorkingState, patch: PreferencePatch) -> dict[str, Any]:
    """Persist only durable (explicit) preferences with provenance.

    Inferences are returned for this turn's search but not written to state.
    """
    turn_local: dict[str, Any] = {}
    provenance = dict(state.preference_provenance or {})

    def _set_durable(key: str, value: object) -> None:
        setattr(state, key, value)
        provenance[key] = "customer_explicit"

    def _turn(key: str, value: object) -> None:
        turn_local[key] = value

    if patch.budget_max is not None:
        if patch.durable:
            _set_durable("budget_max", patch.budget_max)
        else:
            _turn("budget_max", patch.budget_max)
    for key in ("size", "color", "occasion", "style"):
        value = getattr(patch, key)
        if not value:
            continue
        if patch.durable:
            _set_durable(key, value)
        else:
            _turn(key, value)

    state.preference_provenance = provenance
    return turn_local


def preference_search_hints(state: WorkingState, turn_local: dict[str, Any] | None = None) -> str:
    """Compact preference string for catalog.search query enrichment."""
    local = turn_local or {}
    parts: list[str] = []
    budget = local.get("budget_max", state.budget_max)
    if budget is not None:
        parts.append(f"hasta {budget} BOB")
    for key in ("size", "color", "occasion", "style"):
        value = local.get(key) or getattr(state, key, None)
        if value:
            parts.append(str(value))
    return " ".join(parts)
