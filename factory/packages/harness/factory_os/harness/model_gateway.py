from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import quote

import httpx

from factory_os.domain.catalog import STOP
from factory_os.domain.knowledge import brand_fiche, item_plural, item_word, spoken_shop_name
from factory_os.domain.models import NextAction, WorkingState
from factory_os.domain.response_goals import RESPONSE_GOALS
from factory_os.domain.sales_decision import (
    PreferencePatch,
    SalesDecision,
    parse_sales_decision,
    validate_sales_decision,
)
from factory_os.domain.seed import normalize, product_code_tokens, tokenize

logger = logging.getLogger("factory_os.model_gateway")

_GREET = frozenset(
    {
        "hola",
        "holi",
        "holis",
        "buenas",
        "buen",
        "dia",
        "dias",
        "hey",
        "hi",
        "hello",
        "que",
        "tal",
        "como",
        "estas",
        "todo",
        "bien",
    }
)
_BUY = (
    "quiero",
    "me llevo",
    "me lo llevo",
    "confirmo",
    "comprar",
    "cerramos",
    "la quiero",
    "lo quiero",
    "reservame",
    "reservamelo",
)
# product_code_tokens lives in domain.seed (spaced codes like "pago 1").
_PRICE = re.compile(r"\b\d+[.,]\d{2}\b")
_SKU = re.compile(r"\bAC-[A-Z0-9-]+\b", re.I)
_BUSINESS_CODE = re.compile(r"\b[a-z]{1,10}\d+\b", re.I)
# Informal names the model still emits. recommend/compare/request_confirmation are first-class.
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
class ActionProposal:
    action: NextAction
    skill: str
    arguments: dict[str, Any] = field(default_factory=dict)
    provider: str = "heuristic"
    tone: str = "cordial"
    decision: SalesDecision | None = None

    @classmethod
    def from_sales_decision(cls, decision: SalesDecision) -> ActionProposal:
        return cls(
            action=decision.action,
            skill=decision.skill,
            arguments=decision.arguments(),
            provider=decision.provider,
            tone=decision.tone,
            decision=decision,
        )


@dataclass(frozen=True)
class DraftResult:
    text: str
    provider: str
    latency_ms: int = 0
    tokens: int | None = None
    used_fallback: bool = False


class ModelGateway(Protocol):
    def propose(self, *, role: str, context: str, text: str, state: WorkingState) -> ActionProposal | None:
        ...

    def propose_who(self, *, context: str, text: str, state: WorkingState) -> str | None:
        """Return employee role value (sales|cobros|ops|postventa) or None."""
        ...

    def draft(self, *, role: str, context: str, facts: dict[str, Any], fallback: str) -> DraftResult:
        ...

    def staff_answer(self, *, system: str, user: str, fallback: str) -> DraftResult:
        """One staff completion. Deterministic gateways return ``fallback``."""
        ...


def is_fuzzy_greet(text: str) -> bool:
    tokens = tokenize(text) - STOP
    if not tokens:
        return True
    if tokens <= _GREET:
        return True
    for token in tokens:
        if token in _GREET:
            continue
        if len(token) >= 3 and any(word.startswith(token) for word in _GREET):
            continue
        return False
    return True


def heuristic_proposal(state: WorkingState, text: str) -> ActionProposal | None:
    """Deterministic NL hints. Not a permission grant."""
    lowered = normalize(text)
    if is_fuzzy_greet(text):
        return ActionProposal(NextAction.ANSWER, "customer_assistance", provider="heuristic")
    if any(marker in lowered for marker in _BUY) and product_code_tokens(text):
        codes = product_code_tokens(text)
        return ActionProposal(
            NextAction.CREATE_ORDER,
            "sales_closing",
            arguments={"codigo": codes[0]},
            provider="heuristic",
        )
    return None


_PERCENT = re.compile(r"(\d+)\s*%")
_STOCK_CLAIM = re.compile(r"\bstock\s+(\d+)\b|\bquedan\s+(\d+)\b|\b(\d+)\s+unidades\b", re.I)
_MONEY_INT = re.compile(r"(?<![\d.,])(\d+)\s*(?:bob|bs)\b", re.I)
_PAID_CLAIMS = (
    "pago confirmado",
    "pago esta confirmado",
    "pagado por el sistema",
    "ya esta pago",
    "esta pagado",
    "esta confirmado",
    "cobro confirmado",
    "el banco confirmo",
    "confirmado por el banco",
    "ya recibimos tu pago",
    "recibimos tu pago",
    "pago correctamente",
)
_DELIVERY_DONE_CLAIMS = (
    "envio registrado",
    "envío registrado",
    "todo registrado",
    "ya tenemos todo registrado",
    "sera enviada",
    "será enviada",
    "sera enviado",
    "será enviado",
    "pedido registrado",
    "delivery registrado",
)
_PROMO_CLAIMS = (
    "hay promocion",
    "hay descuento",
    "te hago descuento",
    "te descuento",
    "2x1",
    "envio gratis",
)
_POLICY_CLAIMS = (
    "tiene garantia",
    "hay garantia",
    "garantia de",
    "te devolvemos",
    "devolucion inmediata",
    "cambio gratis",
)


def grounding_ok(text: str, facts: dict[str, Any]) -> bool:
    allowed = _allowed_tokens(facts)
    fallback_n = normalize(str(facts.get("fallback") or ""))
    blob = normalize(text)
    for price in _PRICE.findall(text):
        if normalize(price.replace(",", ".")) not in allowed:
            return False
    for amount in _MONEY_INT.findall(text):
        if normalize(amount) not in allowed:
            return False
    for sku in _SKU.findall(text):
        if normalize(sku) not in allowed:
            return False
    for code in _BUSINESS_CODE.findall(text):
        if normalize(code) not in allowed:
            return False
    for match in _STOCK_CLAIM.finditer(text):
        number = next(part for part in match.groups() if part)
        if normalize(number) not in allowed:
            return False
    for percent in _PERCENT.findall(text):
        if f"{percent}%" not in allowed and percent not in allowed:
            return False
    if any(_claimed(blob, phrase) for phrase in _PAID_CLAIMS) and not _flag_or_fallback(
        facts, fallback_n, "payment_status", "confirmed", _PAID_CLAIMS
    ):
        return False
    if any(_claimed(blob, phrase) for phrase in _DELIVERY_DONE_CLAIMS) and not _flag_or_fallback(
        facts, fallback_n, "delivery_ok", True, _DELIVERY_DONE_CLAIMS
    ):
        return False
    if any(_claimed(blob, phrase) for phrase in _PROMO_CLAIMS) and not _flag_or_fallback(
        facts, fallback_n, "promo", True, _PROMO_CLAIMS
    ):
        return False
    if any(_claimed(blob, phrase) for phrase in _POLICY_CLAIMS) and not _flag_or_fallback(
        facts, fallback_n, "policy_ok", True, _POLICY_CLAIMS
    ):
        return False
    return True


_META_DRAFT = (
    "we need to produce",
    "we need to output",
    "only with these facts",
    "no invent price",
    "we have facts",
    "do not say it's paid",
    "do not invent",
    "if missing data",
    "must greet",
    "in prose, no bullets",
    "the instruction:",
    "si en recent",
    "the last adri message",
    "the customer responded",
    "the customer said",
    "response in spanish",
    "using \"tú\" form",
    "using 'tú' form",
    "2-4 sentences",
    "no saludes de nuevo",
    "leer más",
    "system prompt",
    "these instructions",
    "as an ai",
    "borrador",
)
_LEAK_PATTERNS = (
    re.compile(r"\bwe need to\b", re.I),
    re.compile(r"\bas an ai\b", re.I),
    re.compile(r"\bsystem prompt\b", re.I),
    re.compile(r"\bthese instructions\b", re.I),
    re.compile(r"\bsi en recent\b", re.I),
    re.compile(r"\bborrador\b", re.I),
    re.compile(r"^\s*[-•]\s", re.M),
)
_OPENING_GREET = re.compile(
    r"^\s*(¡\s*)?(hola|holi|holis|buen[oa]s(?:\s+d[ií]as?)?|qu[eé]\s+tal|hey)\b",
    re.IGNORECASE,
)
_DRAFT_CTA = (
    "confirmo",
    "me llevo ese",
    "me lo llevo",
    "te armo el pedido",
    "armo el pedido",
)
DRAFT_TEMPERATURE = 0.45
FRIENDLY_WELCOME = (
    "¡Hola! Soy Adri de Authentic Closet. ¿Qué prenda estás buscando hoy?"
)
FRIENDLY_DISCOVERY = (
    "Contame un poco más: ¿qué tipo de prenda, talla o estilo tenés en mente?"
)
FRIENDLY_IDLE_REOPEN = (
    "¡Hola de nuevo! ¿Seguimos con lo que estábamos viendo, o preferís buscar otra cosa?"
)


def _context_idle_reopen(context: str) -> bool:
    return "idle_reopen=true" in context


def _card_value(line: str, key: str) -> str | None:
    prefix = f"{key}="
    if not line.startswith(prefix):
        return None
    value = line.removeprefix(prefix).strip()
    if not value or value == "None":
        return None
    return value


def _csv_card_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def _pipe_card_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split("|") if part.strip()]


def _voice_line_token(line: str, key: str) -> str | None:
    marker = f"{key}="
    start = line.find(marker)
    if start < 0:
        return None
    rest = line[start + len(marker) :].strip()
    token = rest.split(" ", 1)[0] if rest else ""
    if not token or token == "None":
        return None
    return token


def _pack_from_context(context: str) -> dict[str, Any] | None:
    """Shop card lines already compiled into the turn context.

    A missing card keeps today's Closet strings. shop=None is the empty
    profile name from compact_shop_card, not a real shop. Brand crumbs
    (identity, tone, words, traits, examples) rebuild a mini pack for the
    draft system. Address and emojis alone do not.
    """
    shop: str | None = None
    item: str | None = None
    identity: str | None = None
    tone: str | None = None
    words_use: str | None = None
    words_avoid: str | None = None
    traits: str | None = None
    examples: str | None = None
    address: str | None = None
    emojis: str | None = None
    for raw in context.splitlines():
        line = raw.strip()
        if shop is None:
            shop = _card_value(line, "shop")
        if item is None:
            item = _card_value(line, "item")
        if identity is None:
            identity = _card_value(line, "identity")
        if tone is None:
            tone = _card_value(line, "tone")
        if words_use is None:
            words_use = _card_value(line, "words_use")
        if words_avoid is None:
            words_avoid = _card_value(line, "words_avoid")
        if traits is None:
            traits = _card_value(line, "traits")
        if examples is None:
            examples = _card_value(line, "examples")
        if line.startswith("voice="):
            address = address or _voice_line_token(line, "voice")
            emojis = emojis or _voice_line_token(line, "emojis")
            tone = tone or _voice_line_token(line, "tone")
    if shop is None and item is None and not any(
        (identity, tone, words_use, words_avoid, traits, examples)
    ):
        return None
    pack: dict[str, Any] = {}
    profile: dict[str, Any] = {}
    if shop is not None:
        profile["name"] = shop
    if identity is not None:
        profile["summary"] = identity
    if profile:
        pack["profile"] = profile
    if item is not None:
        pack["vocabulary"] = {"item": item}
    voice: dict[str, Any] = {}
    if address is not None:
        voice["address"] = address
    if emojis is not None:
        voice["emojis"] = emojis
    if tone is not None:
        voice["tone"] = tone
    if words_use is not None:
        voice["words_use"] = _csv_card_list(words_use)
    if words_avoid is not None:
        voice["words_avoid"] = _csv_card_list(words_avoid)
    if traits is not None:
        voice["traits"] = _csv_card_list(traits)
    if examples is not None:
        voice["example_replies"] = _pipe_card_list(examples)
    if voice:
        pack["voice"] = voice
    return pack or None


def _welcome_for(pack: dict[str, Any] | None) -> str:
    if pack is None:
        return FRIENDLY_WELCOME
    return (
        f"¡Hola! Soy Adri de {spoken_shop_name(pack)}. "
        f"¿Qué {item_word(pack)} estás buscando hoy?"
    )


def _discovery_for(pack: dict[str, Any] | None) -> str:
    if pack is None:
        return FRIENDLY_DISCOVERY
    return (
        "Contame un poco más: "
        f"¿qué tipo de {item_word(pack)}, talla o estilo tenés en mente?"
    )


def _recent_has_adri_reply(context: str) -> bool:
    """True when compile_context recent already includes an Adri message."""
    in_recent = False
    for line in context.splitlines():
        stripped = line.strip()
        if stripped == "recent:":
            in_recent = True
            continue
        if not in_recent:
            continue
        if stripped.startswith("Adri:"):
            return True
    return False


def _opens_with_greeting(text: str) -> bool:
    return bool(_OPENING_GREET.search(text.lstrip()))


def _draft_adds_cta(text: str) -> bool:
    blob = normalize(text)
    return any(phrase in blob for phrase in _DRAFT_CTA)


def draft_style_ok(text: str, *, context: str = "") -> bool:
    """Follow-up draft contract: no re-greet (unless idle reopen), no automatic closing CTA."""
    if (
        not _context_idle_reopen(context)
        and _recent_has_adri_reply(context)
        and _opens_with_greeting(text)
    ):
        return False
    if _draft_adds_cta(text):
        return False
    return True


def draft_echoes_fallback(text: str, fallback: str) -> bool:
    """True when the model read the canned script back to the customer."""
    spoken = normalize(text)
    script = normalize(fallback)
    if not spoken or not script:
        return False
    if spoken == script:
        return True
    return script in spoken and len(spoken) <= len(script) + 24


def draft_is_catalog_list(text: str) -> bool:
    """True when the reply is a bullet catalog instead of a salesperson turn."""
    bullets = 0
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(("-", "•", "*")):
            bullets += 1
    return bullets >= 2 or text.strip().startswith("Encontré estas opciones")


def draft_leaks_prompt(text: str) -> bool:
    """True when the model echoed system/instruction text instead of customer Spanish."""
    blob = normalize(text)
    if any(marker in blob for marker in _META_DRAFT):
        return True
    if "we need to" in blob or "must be in" in blob:
        return True
    return any(pat.search(text) for pat in _LEAK_PATTERNS)


def soft_draft_fallback(*, context: str, facts: dict[str, Any], operational: str = "") -> str:
    """Customer-facing safety net: never a bullet catalog list."""
    _ = operational
    pack = _pack_from_context(context)
    if _context_idle_reopen(context):
        return FRIENDLY_IDLE_REOPEN
    hits = facts.get("hits") if isinstance(facts.get("hits"), list) else []
    if hits:
        hit = hits[0] if isinstance(hits[0], dict) else {}
        name = str(hit.get("name") or f"esa {item_word(pack)}")
        price = hit.get("price")
        currency = str(hit.get("currency") or "BOB")
        parts = [f"Te destaco {name}"]
        if price is not None and str(price).strip():
            parts.append(f"a {price} {currency}")
        return " ".join(parts) + ". ¿Te sirve esa o afinamos talla o color?"
    if _recent_has_adri_reply(context):
        return _discovery_for(pack)
    return _welcome_for(pack)


def resolve_safe_fallback(fallback: str, facts: dict[str, Any], context: str) -> str:
    """If operational fallback is a catalog script, replace with soft prose."""
    if draft_is_catalog_list(fallback) or "Encontré estas opciones" in fallback:
        return soft_draft_fallback(context=context, facts=facts, operational=fallback)
    return fallback if fallback.strip() else soft_draft_fallback(context=context, facts=facts)


_CODE_MENTION = re.compile(
    r"(?:[ \t]*·[ \t]*|[ \t]*[,;]?[ \t]*)(?:\(|（)?[ \t]*c[oó]digos?[ \t]+"
    r"(?P<code>[a-z]{1,12}\d+[a-z0-9]*)[ \t]*(?:\)|）)?",
    re.I,
)


def _codes_the_customer_said(context: str) -> set[str]:
    said: list[str] = []
    for line in context.splitlines():
        stripped = line.strip()
        lower = stripped.lower()
        if lower.startswith("customer:"):
            said.extend(product_code_tokens(stripped.split(":", 1)[1]))
    return {code.lower() for code in said}


def hide_catalog_codes(text: str, facts: dict[str, Any], context: str = "") -> str:
    """Browse replies name the garment. The code is spoken at payment, or if the client brought it (live)."""
    if facts.get("mention_code"):
        return text
    keep = _codes_the_customer_said(context)
    for raw in facts.get("keep_codes") or []:
        keep.add(str(raw).strip().lower())

    def _drop_phrase(match: re.Match[str]) -> str:
        if match.group("code").lower() in keep:
            return match.group(0)
        return ""

    out = _CODE_MENTION.sub(_drop_phrase, text)
    out = re.sub(r"\(\s*\)", "", out)
    out = re.sub(r"\s+([,.;])", r"\1", out)
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r" +([.!?])", r"\1", out)
    return out.strip()


def grounded_draft(text: str, facts: dict[str, Any], fallback: str, context: str = "") -> str:
    safe = resolve_safe_fallback(fallback, facts, context)
    if draft_leaks_prompt(text):
        chosen = safe
    elif not text.strip() or draft_is_catalog_list(text):
        chosen = safe
    elif not draft_style_ok(text, context=context) or not grounding_ok(text, facts):
        chosen = safe
    else:
        chosen = text.strip()
    return hide_catalog_codes(chosen, facts, context)


def _usable_draft(
    raw: str | None, facts: dict[str, Any], fallback: str, context: str
) -> tuple[str | None, bool]:
    _ = fallback
    if not raw or not raw.strip():
        return None, False
    if draft_leaks_prompt(raw) or draft_is_catalog_list(raw):
        return None, False
    if not grounding_ok(raw, facts) or not draft_style_ok(raw, context=context):
        return None, False
    return raw.strip(), True


def _prefer_spoken_draft(first: str | None, second: str | None, fallback: str) -> str | None:
    """Prefer a reply that is not the script and not a bullet catalog."""
    for candidate in (second, first):
        if candidate and not draft_echoes_fallback(candidate, fallback) and not draft_is_catalog_list(candidate):
            if not draft_leaks_prompt(candidate):
                return candidate
    for candidate in (second, first):
        if candidate and not draft_echoes_fallback(candidate, fallback) and not draft_leaks_prompt(candidate):
            return candidate
    return None


def render_reply(
    gateway: ModelGateway | None,
    *,
    role: str,
    context: str,
    fallback: str,
    facts: dict[str, Any] | None = None,
) -> str:
    """Draft then verify. The gateway never authorizes tools."""
    desk = gateway or FakeGateway()
    payload = dict(facts or {})
    payload["fallback"] = fallback
    drafted = desk.draft(role=role, context=context, facts=payload, fallback=fallback)
    # Deterministic desks (FakeGateway / test stubs) keep operational scripts.
    if getattr(desk, "is_deterministic", False):
        return drafted.text
    safe = resolve_safe_fallback(fallback, payload, context)
    return grounded_draft(drafted.text, payload, safe, context=context)


def _claimed(blob: str, phrase: str) -> bool:
    start = 0
    while True:
        pos = blob.find(phrase, start)
        if pos < 0:
            return False
        prefix = blob[max(0, pos - 16) : pos]
        if re.search(r"\bno(?:\s+\w+){0,4}\s*$", prefix) or prefix.endswith("sin "):
            start = pos + 1
            continue
        return True


def _flag_or_fallback(
    facts: dict[str, Any],
    fallback_n: str,
    key: str,
    expected: object,
    phrases: tuple[str, ...],
) -> bool:
    if facts.get(key) == expected:
        return True
    return any(phrase in fallback_n for phrase in phrases)


def _allowed_tokens(facts: dict[str, Any]) -> set[str]:
    allowed: set[str] = set()

    def _add(raw: object) -> None:
        text = str(raw).strip()
        if not text:
            return
        canon = normalize(text.replace(",", "."))
        allowed.add(canon)
        if "." in canon:
            allowed.add(canon.split(".", 1)[0])
        if canon.endswith("%"):
            allowed.add(canon.removesuffix("%"))

    fallback = facts.get("fallback") or ""
    for price in _PRICE.findall(fallback):
        _add(price.replace(",", "."))
    for sku in _SKU.findall(fallback):
        _add(sku)
    for code in _BUSINESS_CODE.findall(fallback):
        _add(code)
    for match in _STOCK_CLAIM.finditer(fallback):
        number = next(part for part in match.groups() if part)
        _add(number)
    for percent in _PERCENT.findall(fallback):
        _add(f"{percent}%")
        _add(percent)
    for hit in facts.get("hits") or []:
        if not isinstance(hit, dict):
            continue
        for key in ("price", "codigo", "product_sku", "variant_sku", "stock", "name", "currency"):
            if hit.get(key) is None or hit.get(key) == "":
                continue
            _add(hit[key])
    for key in ("price", "codigo", "sku", "name", "currency", "stock", "address"):
        if facts.get(key) is None or facts.get(key) == "":
            continue
        _add(facts[key])
    for promo in facts.get("promos") or []:
        _add(promo)
    return allowed


def parse_proposal(raw: str, provider: str) -> ActionProposal | None:
    try:
        payload = json.loads(_extract_json(raw))
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    decision = parse_sales_decision(payload, provider=provider)
    if decision is None:
        return None
    errors = validate_sales_decision(decision)
    if errors:
        # Drop illegal tools but keep the commercial action when possible.
        if decision.tool_call and any("tool not allowed" in err for err in errors):
            decision = SalesDecision(
                action=decision.action,
                skill=decision.skill,
                understanding=decision.understanding,
                preference_patch=decision.preference_patch,
                tool_call=None,
                response_goal=decision.response_goal,
                provider=decision.provider,
                tone=decision.tone,
            )
            errors = validate_sales_decision(decision)
        if errors:
            return None
    return ActionProposal.from_sales_decision(decision)


def _extract_json(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).removesuffix("```").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]
    return text


class FakeGateway:
    """Deterministic. Pytest never hits the network.

    Simulates a structured SalesDecision (ADR-003): always returns a proposal,
    built from the same commercial fallback the live path uses when the model fails.
    """

    is_deterministic = True

    def __init__(self, trace_log: Any | None = None) -> None:
        self.trace_log = trace_log
        self.last_event: dict[str, Any] = {}

    def propose(self, *, role: str, context: str, text: str, state: WorkingState) -> ActionProposal | None:
        _ = context
        role_key = (role or "").strip().lower()
        if role_key in {"collections", "cobros"}:
            return self._propose_cobros(text)
        if role_key in {"ops", "operaciones"}:
            return self._propose_ops(text, state)
        from factory_os.agents.sales_heuristics import next_best_action

        hinted = heuristic_proposal(state, text)
        if hinted is not None and hinted.action is NextAction.CREATE_ORDER:
            decision = SalesDecision(
                action=hinted.action,
                skill=hinted.skill,
                understanding="cliente nombra código y quiere comprar",
                preference_patch=PreferencePatch(),
                tool_call={"name": "order.create", "arguments": dict(hinted.arguments)},
                response_goal="",
                provider="fake",
            )
        else:
            action, skill = next_best_action(state, text)
            tool_call = None
            if action is NextAction.SEARCH_CATALOG:
                tool_call = {"name": "catalog.search", "arguments": {"query": text}}
            elif action is NextAction.CREATE_ORDER:
                tool_call = {"name": "order.create", "arguments": {}}
            elif action is NextAction.ADD_TO_CART:
                tool_call = {"name": "cart.add", "arguments": {}}
            decision = SalesDecision(
                action=action,
                skill=skill,
                understanding="",
                preference_patch=PreferencePatch(),
                tool_call=tool_call,
                response_goal="",
                provider="fake",
            )
        result = ActionProposal.from_sales_decision(decision)
        self.last_event = {
            "op": "propose",
            "provider": "fake",
            "model": None,
            "latency_ms": 0,
            "tokens": None,
            "fallback": None,
            "parsed": True,
            "used_fallback": False,
            "error": None,
            "sales_decision": True,
        }
        if self.trace_log is not None:
            self.trace_log.record(
                "propose",
                provider="fake",
                model=None,
                latency_ms=0,
                used_fallback=False,
                prompt=None,
                raw_response=None,
                parsed_action=result.action.value,
                parsed_skill=result.skill,
                payload={
                    "parse_success": True,
                    "result_provider": result.provider,
                    "client_text": text,
                    "sales_decision": True,
                    "understanding": decision.understanding,
                    "response_goal": decision.response_goal,
                },
            )
        return result

    def _propose_cobros(self, text: str) -> ActionProposal:
        blob = normalize(text)
        op = "wait"
        if blob.strip() == "reenviame el qr" or (("reenvi" in blob) and "qr" in blob):
            op = "resend_qr"
        return ActionProposal(
            NextAction.ANSWER,
            "payment_verification",
            arguments={"op": op},
            provider="fake",
        )

    def _propose_ops(self, text: str, state: WorkingState) -> ActionProposal:
        """Simulate Ops intent for pytest: extract shipping fields into the proposal."""
        _ = state
        import re

        name = None
        address = None
        name_m = re.search(
            r"(?:me llamo|soy|nombre(?: es)?)\s+([A-Za-zÁÉÍÓÚáéíóúñÑ ]{2,40})",
            text or "",
            re.I,
        )
        if name_m:
            name = name_m.group(1).strip()
        maps = re.search(
            r"ubicacion maps:\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)(?:\s*\(([^)]*)\))?",
            text or "",
            re.I,
        )
        if maps:
            lat, lon = maps.group(1), maps.group(2)
            label = (maps.group(3) or "").strip()
            address = (
                f"{label} (Maps {lat},{lon})"
                if label and label.lower() not in {"ubicacion", "ubicación"}
                else f"Maps {lat},{lon}"
            )
        else:
            addr_m = re.search(
                r"(?:vivo en|direcci[oó]n(?: es)?|enviar a)\s+(.+)$",
                text or "",
                re.I,
            )
            if addr_m:
                address = addr_m.group(1).strip()
        args: dict[str, Any] = {"op": "ask_shipping"}
        if name:
            args["name"] = name
        if address:
            args["address"] = address
        if name and address:
            args["op"] = "create_delivery"
        hour = re.search(r"\ba las\s+(\d{1,2}(?::\d{2})?)", text or "", re.I)
        if hour:
            args["delivery_window"] = f"a las {hour.group(1)}"
        elif re.search(r"(?:en|por) la ma[nñ]ana", text or "", re.I):
            args["delivery_window"] = "en la mañana"
        return ActionProposal(
            NextAction.ANSWER,
            "customer_delivery_data",
            arguments=args,
            provider="fake",
        )

    def propose_who(self, *, context: str, text: str, state: WorkingState) -> str | None:
        """Fake WHO: simulate Gemini intent for pytest (not a live product keyword router)."""
        _ = context
        blob = normalize(text)
        codes = product_code_tokens(text)
        # Postventa: damage / claim intent
        if any(
            p in blob
            for p in (
                "roto",
                "rotas",
                "incidencia",
                "danado",
                "danada",
                "reclamo",
                "devolucion",
                "garantia",
            )
        ) or ("llego" in blob and ("pedido" in blob or "ayer" in blob or "roto" in blob)):
            who = "postventa"
        elif codes and state.order_id is None:
            # Exact product/live code → Adri closes; never Cobros just because "pago"∈"pago1".
            who = "sales"
        elif state.order_id is not None and state.payment_id is not None:
            # A question about the garment, with a QR already out, goes back to Adri.
            aside = any(
                word in blob
                for word in ("tela", "talla", "color", "foto", "material", "industria")
            )
            paying = "comprobante" in blob or "ya pague" in blob or "ya pagué" in blob
            if aside and not paying:
                who = "sales"
            elif state.folder and state.folder.to is not None:
                who = state.folder.to.value
                if who == "collections":
                    who = "cobros"
            elif state.graph_node in {"operaciones", "cobros", "adri", "postventa"}:
                who = {
                    "operaciones": "ops",
                    "cobros": "cobros",
                    "adri": "sales",
                    "postventa": "postventa",
                }[state.graph_node]
            elif any(
                w in blob
                for w in ("envio", "envío", "direccion", "dirección", "maps", "entrega", "me llamo", "vivo")
            ) or "ubicacion maps" in blob:
                who = "ops"
            elif any(
                w in blob.split()
                for w in ("pago", "pague", "pagué", "qr", "transfer", "transferí", "transferi")
            ) or "ya pague" in blob or "ya pagué" in blob or "comprobante" in blob:
                who = "cobros"
            else:
                who = "ops" if state.stage and state.stage.value == "purchased" else "cobros"
        elif state.order_id is not None:
            who = "cobros"
        elif state.handoff is not None:
            who = state.handoff.value
            if who == "collections":
                who = "cobros"
        else:
            who = "sales"

        self.last_event = {
            "op": "propose_who",
            "provider": "fake",
            "parsed": True,
            "used_fallback": False,
        }
        if self.trace_log is not None:
            self.trace_log.record(
                "propose_who",
                provider="fake",
                used_fallback=False,
                payload={"client_text": text, "parse_success": True, "employee": who},
            )
        return who

    def draft(self, *, role: str, context: str, facts: dict[str, Any], fallback: str) -> DraftResult:
        _ = role
        self.last_event = {
            "op": "draft",
            "provider": "fake",
            "model": None,
            "latency_ms": 0,
            "tokens": None,
            "fallback": None,
            "used_fallback": True,
            "grounding_ok": True,
            "error": None,
        }
        if self.trace_log is not None:
            self.trace_log.record(
                "draft",
                provider="fake",
                model=None,
                latency_ms=0,
                used_fallback=True,
                prompt=None,
                raw_response=None,
                payload={
                    "fallback_text": fallback,
                    "facts": facts,
                    "compile_context": context,
                    "raw_draft": None,
                    "grounding_ok": True,
                    "final_rendered_reply": fallback,
                },
            )
        return DraftResult(text=fallback, provider="fake", used_fallback=True)

    def staff_answer(self, *, system: str, user: str, fallback: str) -> DraftResult:
        _ = (system, user)
        self.last_event = {
            "op": "staff_answer",
            "provider": "fake",
            "model": None,
            "latency_ms": 0,
            "tokens": None,
            "fallback": None,
            "used_fallback": True,
            "error": None,
        }
        if self.trace_log is not None:
            self.trace_log.record(
                "staff_answer",
                provider="fake",
                model=None,
                latency_ms=0,
                used_fallback=True,
                prompt=None,
                raw_response=None,
                payload={
                    "fallback_text": fallback,
                    "final_rendered_reply": fallback,
                },
            )
        return DraftResult(text=fallback, provider="fake", used_fallback=True)


class HttpProvider:
    def __init__(self, name: str, complete, model_id: str = "") -> None:
        self.name = name
        self.complete = complete
        self.model_id = model_id


class FailoverGateway:
    is_deterministic = False

    def __init__(
        self,
        providers: list[HttpProvider],
        timeout_s: float = 8.0,
        trace_log: Any | None = None,
    ) -> None:
        self._providers = providers
        self._timeout_s = timeout_s
        self._heuristic = FakeGateway(trace_log=None)
        self.last_event: dict[str, Any] = {}
        self.trace_log = trace_log
        self._models = {provider.name: provider.model_id for provider in providers}

    def propose(self, *, role: str, context: str, text: str, state: WorkingState) -> ActionProposal | None:
        system, user = _propose_messages(role, context, text)
        raw, provider, latency_ms, tokens, fallback_from, error = self._complete(system, user)
        parsed = parse_proposal(raw, provider) if raw else None
        used_fallback = parsed is None
        result = parsed if parsed is not None else self._heuristic.propose(
            role=role, context=context, text=text, state=state
        )
        prompt = f"[system]\n{system}\n[user]\n{user}"
        self.last_event = {
            "op": "propose",
            "provider": provider,
            "model": self._models.get(provider) or None,
            "latency_ms": latency_ms,
            "tokens": tokens,
            "fallback": fallback_from,
            "parsed": parsed is not None,
            "used_fallback": used_fallback,
            "error": error,
        }
        if self.trace_log is not None:
            self.trace_log.record(
                "propose",
                provider=provider if not used_fallback else (fallback_from or provider),
                model=self._models.get(provider) or (
                    self._models.get(fallback_from or "") if fallback_from else None
                ),
                latency_ms=latency_ms,
                used_fallback=used_fallback,
                prompt=prompt,
                raw_response=raw,
                parsed_action=result.action.value if result else None,
                parsed_skill=result.skill if result else None,
                error=error,
                payload={
                    "parse_success": parsed is not None,
                    "network_provider": provider,
                    "failover_from": fallback_from,
                    "tokens": tokens,
                    "client_text": text,
                    "result_provider": result.provider if result else None,
                },
            )
        return result

    def propose_who(self, *, context: str, text: str, state: WorkingState) -> str | None:
        system, user = _propose_who_messages(context, text, state)
        raw, provider, latency_ms, tokens, fallback_from, error = self._complete(system, user)
        role = parse_who_proposal(raw) if raw else None
        used_fallback = role is None
        prompt = f"[system]\n{system}\n[user]\n{user}"
        self.last_event = {
            "op": "propose_who",
            "provider": provider,
            "model": self._models.get(provider) or None,
            "latency_ms": latency_ms,
            "tokens": tokens,
            "fallback": fallback_from,
            "parsed": role is not None,
            "used_fallback": used_fallback,
            "error": error,
        }
        if self.trace_log is not None:
            self.trace_log.record(
                "propose_who",
                provider=provider if not used_fallback else (fallback_from or provider),
                model=self._models.get(provider) or None,
                latency_ms=latency_ms,
                used_fallback=used_fallback,
                prompt=prompt,
                raw_response=raw,
                parsed_action=role,
                error=error,
                payload={
                    "parse_success": role is not None,
                    "client_text": text,
                    "proposed_role": role,
                    "tokens": tokens,
                },
            )
        return role

    def draft(self, *, role: str, context: str, facts: dict[str, Any], fallback: str) -> DraftResult:
        facts_with_fallback = {**facts, "fallback": fallback}
        safe = resolve_safe_fallback(fallback, facts_with_fallback, context)
        system, user = _draft_messages(role, context, facts)
        prompt = f"[system]\n{system}\n[user]\n{user}"
        raw, provider, latency_ms, tokens, fallback_from, error = self._complete(
            system, user, temperature=DRAFT_TEMPERATURE
        )
        chosen, ok = _usable_draft(raw, facts_with_fallback, safe, context)
        retried = False
        raw_retry: str | None = None
        if chosen is None or draft_echoes_fallback(chosen, safe) or draft_is_catalog_list(chosen or ""):
            retried = True
            nudge_user = (
                user
                + "\n\nEl intento anterior no sirvió. Escribí solo el mensaje al cliente "
                "en prosa, sin viñetas ni explicar reglas."
            )
            raw_retry, retry_provider, retry_ms, retry_tokens, retry_from, retry_error = self._complete(
                system, nudge_user, temperature=DRAFT_TEMPERATURE
            )
            latency_ms += retry_ms
            tokens = (tokens or 0) + (retry_tokens or 0)
            if retry_from:
                fallback_from = retry_from
            if retry_error and not error:
                error = retry_error
            if retry_provider != "none":
                provider = retry_provider
            retry_text, retry_ok = _usable_draft(raw_retry, facts_with_fallback, safe, context)
            if retry_ok:
                ok = True
            chosen = _prefer_spoken_draft(chosen, retry_text, safe)
        used = chosen is None
        text = safe if used else chosen
        result = DraftResult(
            text=text,
            provider="fixed" if used else provider,
            latency_ms=latency_ms,
            tokens=tokens,
            used_fallback=used,
        )
        self.last_event = {
            "op": "draft",
            "provider": result.provider,
            "model": self._models.get(provider) or None,
            "latency_ms": latency_ms,
            "tokens": tokens,
            "fallback": fallback_from,
            "used_fallback": result.used_fallback,
            "grounding_ok": ok and not used,
            "error": error,
        }
        if self.trace_log is not None:
            self.trace_log.record(
                "draft",
                provider=result.provider,
                model=self._models.get(provider) or None,
                latency_ms=latency_ms,
                used_fallback=result.used_fallback,
                prompt=prompt,
                raw_response=raw_retry or raw,
                error=error,
                payload={
                    "fallback_text": fallback,
                    "safe_fallback": safe,
                    "facts": facts,
                    "compile_context": context,
                    "raw_draft": raw,
                    "raw_retry": raw_retry,
                    "retried": retried,
                    "grounding_ok": ok and not used,
                    "draft_style_ok": draft_style_ok(text, context=context) if text else False,
                    "final_rendered_reply": result.text,
                    "tokens": tokens,
                    "failover_from": fallback_from,
                    "network_provider": provider,
                },
            )
        return result

    def staff_answer(self, *, system: str, user: str, fallback: str) -> DraftResult:
        """One completion for the internal Analista. Empty output keeps the fallback."""
        prompt = f"[system]\n{system}\n[user]\n{user}"
        raw, provider, latency_ms, tokens, fallback_from, error = self._complete(system, user)
        text = (raw or "").strip()
        used = not text
        result = DraftResult(
            text=fallback if used else text,
            provider="fixed" if used else provider,
            latency_ms=latency_ms,
            tokens=tokens,
            used_fallback=used,
        )
        self.last_event = {
            "op": "staff_answer",
            "provider": result.provider,
            "model": self._models.get(provider) or None,
            "latency_ms": latency_ms,
            "tokens": tokens,
            "fallback": fallback_from,
            "used_fallback": result.used_fallback,
            "error": error,
        }
        if self.trace_log is not None:
            self.trace_log.record(
                "staff_answer",
                provider=result.provider,
                model=self._models.get(provider) or None,
                latency_ms=latency_ms,
                used_fallback=result.used_fallback,
                prompt=prompt,
                raw_response=raw,
                error=error,
                payload={
                    "fallback_text": fallback,
                    "final_rendered_reply": result.text,
                    "tokens": tokens,
                    "failover_from": fallback_from,
                },
            )
        return result

    def _complete(
        self, system: str, user: str, *, temperature: float = 0.2
    ) -> tuple[str | None, str, int, int | None, str | None, str | None]:
        fallback_from = None
        last_error: str | None = None
        started = time.perf_counter()
        for provider in self._providers:
            hop = time.perf_counter()
            try:
                text, tokens = provider.complete(system, user, self._timeout_s, temperature)
                latency_ms = int((time.perf_counter() - hop) * 1000)
                logger.info(
                    "model_gateway op=complete provider=%s ms=%s tokens=%s fallback_from=%s",
                    provider.name,
                    latency_ms,
                    tokens,
                    fallback_from,
                )
                return text, provider.name, latency_ms, tokens, fallback_from, None
            except Exception as exc:
                fallback_from = provider.name
                last_error = f"{type(exc).__name__}: {exc}"
                logger.info("model_gateway failover from=%s err=%s", provider.name, type(exc).__name__)
        latency_ms = int((time.perf_counter() - started) * 1000)
        return None, "none", latency_ms, None, fallback_from, last_error


DRAFT_SYSTEM = """\
Sos Adri, vendedora de Authentic Closet por WhatsApp.
Español de Bolivia, trato de tú, 2 a 4 oraciones, prosa corrida (sin viñetas ni markdown).
Usá SOLO los datos en FACTS para precio o stock. No inventes promoción, garantía ni forma de pago.
No digas el código de catálogo (h001, s018, etc.) mientras el cliente mira prendas: nombrá la prenda, el precio, la talla y el color.
El código se dice solo si el cliente lo escribió (viene de un live) o si FACTS trae mention_code=true (ya se arma el pago).
No digas "confirmo", "me llevo ese" ni "te armo el pedido".
Si el cliente no mencionó una prenda, hacé una sola pregunta. Si hay prendas en FACTS, recomendá una opción concreta.
Respondé ÚNICAMENTE con el mensaje final para el cliente — sin explicar estas reglas, sin razonar en voz alta, sin mencionar que sos una IA."""

PROPOSE_WHO_SYSTEM = """\
Sos el orquestador de empleados digitales de Authentic Closet (WHO).
Elegí un solo empleado según la intención del cliente y la línea ESTADO. Respondé SOLO JSON:
{"employee":"sales|cobros|ops|postventa","reason":"..."}
Orden de prioridad (la primera que aplique manda):
1. reclamo, pedido dañado o garantía → postventa
2. pago_confirmado=sí y habla de envío, dirección, hora o ubicación → ops
3. QR, comprobante, o pregunta de pago con reserva o QR → cobros
4. el resto → sales
sales = Adri (vende, descubre, recomienda, suma al carrito).
Si ya hay QR y pregunta por la prenda (tela, talla, color, fotos), elegí sales.
Un código de live/prenda (ej. pago1, h001) NO es un cobro: eso es sales.
No inventes que el pago está confirmado. Sin reserva ni QR → no elijas ops ni cobros."""


def _propose_who_system(pack: dict[str, Any] | None) -> str:
    if pack is None:
        return PROPOSE_WHO_SYSTEM
    shop = spoken_shop_name(pack)
    if shop == "Authentic Closet":
        return PROPOSE_WHO_SYSTEM
    return PROPOSE_WHO_SYSTEM.replace("Authentic Closet", shop, 1)


def _draft_rules(item: str, items: str) -> str:
    return (
        "Usá SOLO los datos en FACTS para precio o stock. "
        "No inventes promoción, garantía ni forma de pago.\n"
        "No digas el código de catálogo (h001, s018, etc.) mientras el cliente "
        f"mira {items}: nombrá la {item}, el precio, la talla y el color.\n"
        "El código se dice solo si el cliente lo escribió (viene de un live) "
        "o si FACTS trae mention_code=true (ya se arma el pago).\n"
        'No digas "confirmo", "me llevo ese" ni "te armo el pedido".\n'
        f"Si el cliente no mencionó una {item}, hacé una sola pregunta. "
        f"Si hay {items} en FACTS, recomendá una opción concreta.\n"
        "Respondé ÚNICAMENTE con el mensaje final para el cliente — "
        "sin explicar estas reglas, sin razonar en voz alta, sin mencionar que sos una IA."
    )


def _draft_system(pack: dict[str, Any] | None) -> str:
    if pack is None:
        return DRAFT_SYSTEM
    shop = spoken_shop_name(pack)
    item = item_word(pack)
    items = item_plural(pack)
    fiche = brand_fiche(pack).strip()
    rules = _draft_rules(item, items)
    if not fiche:
        return (
            f"Sos Adri, vendedora de {shop} por WhatsApp.\n"
            "Español de Bolivia, trato de tú, 2 a 4 oraciones, prosa corrida "
            "(sin viñetas ni markdown).\n"
            f"{rules}"
        )
    address = str(((pack.get("voice") or {}).get("address") or "")).strip().lower()
    trato = "trato de usted" if address == "usted" else "trato de tú"
    return (
        f"Sos Adri, vendedora de {shop} por WhatsApp.\n"
        f"{fiche}\n"
        "Cuando uses una FAQ o política, dilo con tus palabras; "
        "no copies un reglamento. No recitees visión ni misión.\n"
        f"Español de Bolivia, {trato}, 2 a 4 oraciones, prosa corrida "
        "(sin viñetas ni markdown).\n"
        f"{rules}"
    )


_PAYMENT_CONFIRMED_IN_CONTEXT = re.compile(
    r"(?:^|\s)payment=confirmed(?:\s|$)",
    re.IGNORECASE,
)


def _who_payment_confirmed(state: WorkingState, context: str) -> bool:
    """True only when the folder or compiled context says the bank confirmed.

    A set folder.payment_state wins, so a pending folder is not confirmed even
    if an older context line still says payment=confirmed. QR and payment_id
    are not confirmation. This does not read the store.
    """
    raw = ""
    folder = state.folder
    if folder is not None and folder.payment_state:
        raw = str(folder.payment_state).strip().lower()
    if raw:
        return raw == "confirmed"
    return bool(context and _PAYMENT_CONFIRMED_IN_CONTEXT.search(context))


def _who_estado_line(state: WorkingState, context: str) -> str:
    cart = "sí" if state.cart else "no"
    qr = "sí" if state.provider_ref or state.payment_id else "no"
    paid = "sí" if _who_payment_confirmed(state, context) else "no"
    return f"ESTADO: carrito={cart}, qr_emitido={qr}, pago_confirmado={paid}"


def _propose_who_messages(context: str, text: str, state: WorkingState) -> tuple[str, str]:
    sticky = state.graph_node or (state.last_employee.value if state.last_employee else "none")
    user = (
        f"{_who_estado_line(state, context)}\n"
        f"checkpoint_node={sticky}\n{context}\ncliente: {text}\n"
    )
    return _propose_who_system(_pack_from_context(context)), user


def parse_who_proposal(raw: str) -> str | None:
    try:
        payload = json.loads(_extract_json(raw))
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    from factory_os.agents.orchestrator import parse_who_role

    role = parse_who_role(str(payload.get("employee") or payload.get("role") or ""))
    return role.value if role is not None else None


def _adapt_sales_decision_system(system: str, pack: dict[str, Any] | None) -> str:
    """Shop name and item noun from the compiled card.

    A missing card, or Authentic Closet with item prenda, keeps the Closet
    string byte for byte. Another shop only rewrites the opening line. Another
    item rewrites the sales noun phrases; clothing examples stay.
    """
    if pack is None:
        return system
    shop = spoken_shop_name(pack)
    item = item_word(pack)
    if shop == "Authentic Closet" and item == "prenda":
        return system
    if shop != "Authentic Closet":
        system = system.replace(
            "Sos el vendedor digital (autoridad conversacional). "
            "No tenés autoridad operacional.",
            (
                f"Sos Adri, vendedora de {shop}. Autoridad conversacional. "
                "No tenés autoridad operacional."
            ),
            1,
        )
    if item == "prenda":
        return system
    if item.endswith("a"):
        indefinite, other, concrete = "una", "otra", "concreta"
    else:
        indefinite, other, concrete = "un", "otro", "concreto"
    plural = item_plural(pack)
    system = system.replace("Si quiere otra prenda", f"Si quiere {other} {item}", 1)
    system = system.replace(
        "de una prenda concreta",
        f"de {indefinite} {item} {concrete}",
        1,
    )
    system = system.replace("live/prenda", f"live/{item}", 1)
    system = system.replace("1–3 prendas", f"1–3 {plural}", 1)
    system = system.replace("mostraste una prenda", f"mostraste {indefinite} {item}", 1)
    return system


def _propose_messages(role: str, context: str, text: str) -> tuple[str, str]:
    role_key = (role or "").strip().lower()
    if role_key in {"collections", "cobros"}:
        system = (
            "Sos Cobros. Autoridad conversacional; el runtime autoriza pagos.\n"
            "Respondé SOLO JSON:\n"
            '{"action":"answer","skill":"payment_verification",'
            '"tool_call":{"name":"","arguments":{"op":"wait|resend_qr|check_status"}},'
            '"response_goal":"..."}\n'
            "op=resend_qr solo si el cliente pide reenviar el QR. "
            "op=check_status si pregunta si ya pagó. "
            "op=wait si solo espera. "
            "Nunca marques el pago como confirmado: solo el banco lo hace.\n"
        )
        return system, f"role=cobros\n{context}\ncliente: {text}\n"
    if role_key in {"ops", "operaciones"}:
        system = (
            "Sos Operaciones (envíos). Autoridad conversacional; el runtime registra el envío.\n"
            "Respondé SOLO JSON:\n"
            '{"action":"answer","skill":"customer_delivery_data",'
            '"tool_call":{"name":"delivery.create","arguments":'
            '{"op":"ask_shipping|create_delivery","name":null,"address":null}},'
            '"response_goal":"..."}\n'
            "Si el cliente dio nombre, ponelo en arguments.name. "
            "Si dio dirección o pin Maps, en arguments.address. "
            "Si dio una hora o la mañana/tarde, arguments.delivery_window con ese texto. "
            "op=create_delivery solo cuando tengas nombre y dirección. "
            "No inventes dirección ni marques pago.\n"
        )
        return system, f"role=ops\n{context}\ncliente: {text}\n"
    actions = ", ".join(item.value for item in NextAction)
    goal_codes = ", ".join(code for code, _phrase in RESPONSE_GOALS)
    system = (
        "Sos el vendedor digital (autoridad conversacional). No tenés autoridad operacional.\n"
        "Respondé SOLO un JSON SalesDecision:\n"
        '{"action":"...","skill":"...","understanding":"...","preference_patch":'
        '{"budget_max":null,"size":null,"color":null,"occasion":null,"style":null,"durable":false},'
        '"tool_call":{"name":"...","arguments":{}},"response_goal":"..."}\n'
        f"action debe ser uno de: {actions}\n"
        f"response_goal debe ser uno de estos códigos: {goal_codes}. "
        "Nunca inventes jerga ni texto libre en response_goal.\n"
        "Prioridad (la primera situación que aplique manda):\n"
        "| situación | action | response_goal |\n"
        "| reclamo, pide persona o nada encaja | escalate o handoff | |\n"
        "| saluda | answer | greet |\n"
        "| pregunta delivery, horario, pago QR, devoluciones, TikTok o quiénes somos "
        "| answer | shop_faq |\n"
        "| dice caro o carísimo SIN monto | handle_objection | handle_price_objection |\n"
        "| da presupuesto CON monto | search_catalog | | preference_patch.budget_max y durable=true |\n"
        "| solo categoría (blusas, vestidos, faldas…) sin detalle | ask_discovery_question | ask_detail |\n"
        "| categoría + detalle, o busca sin código de live/prenda | search_catalog o recommend "
        "| show_options o recommend_ask_fit | ofrecé 1\u20133 prendas |\n"
        "| código + pregunta de precio, talla o color de una prenda concreta | search_catalog | |\n"
        "| código + quiere esa | create_order | | arguments.codigo |\n"
        "| ya mostraste una prenda y el mensaje expresa querer comprarla "
        "(no un simple ok de acuse) | create_order | |\n"
        "| Si quiere otra prenda y aún no pagar | add_to_cart | |\n"
        "compare y request_confirmation solo si pide comparar o confirmar antes de pagar.\n"
        "clarify_payment si hay que explicar el QR sin confirmar el pago. "
        "confirm_intent antes de cobrar cuando todavía no dijo que quiere esa. "
        "restart si quiere empezar de cero.\n"
        "No pidas payment.create_qr: Adri no cobra. "
        "cart.add suma sin cobrar. order.create pasa a Cobros. "
        "send_product_image manda la foto principal del catálogo; arguments solo product_sku "
        "(id de producto, p.ej. h001). Nunca pases url, path ni caption.\n"
        "Si el cliente pide el pedido para otro día, arguments.fulfill_on es YYYY-MM-DD "
        "y el stock de hoy no se resta.\n"
        "preference_patch.durable=true solo si el cliente lo dijo explícito; "
        "inferencias con durable=false (no se guardan como hechos).\n"
        "No inventes precio, stock, SKU ni pago.\n"
    )
    if role == "sales":
        system = _adapt_sales_decision_system(system, _pack_from_context(context))
    user = f"role={role}\n{context}\ncliente: {text}\n"
    return system, user


def _facts_for_draft(facts: dict[str, Any]) -> dict[str, Any]:
    """The draft model does not see catalog codes while the client is browsing."""
    shown = {key: value for key, value in facts.items() if key != "fallback"}
    if shown.get("mention_code"):
        return shown
    hits = shown.get("hits")
    if not isinstance(hits, list):
        return shown
    cleaned: list[Any] = []
    for hit in hits:
        if isinstance(hit, dict):
            cleaned.append({key: value for key, value in hit.items() if key != "codigo"})
        else:
            cleaned.append(hit)
    shown["hits"] = cleaned
    return shown


def _draft_messages(role: str, context: str, facts: dict[str, Any]) -> tuple[str, str]:
    shown = _facts_for_draft(facts)
    goal = str(shown.get("response_goal") or "").strip()
    parts = [f"role={role}", context, f"FACTS: {json.dumps(shown, ensure_ascii=False)}"]
    if goal:
        parts.insert(0, f"Objetivo de este turno: {goal}")
    if _context_idle_reopen(context):
        parts.append(
            "(Idle reopen: saludá breve y preguntá si quiere continuar lo anterior "
            "o buscar otra cosa. Una sola pregunta; sin catálogo ni pitch.)"
        )
    elif _recent_has_adri_reply(context):
        parts.append("(No repitas el saludo; ya se saludaron en este chat.)")
    if shown.get("mention_code"):
        parts.append("(Momento de pago: nombrá el código de la prenda que se va a cobrar.)")
    else:
        parts.append("(No menciones códigos de catálogo que el cliente no escribió.)")
    return _draft_system(_pack_from_context(context)), "\n\n".join(parts)


def _gemini_complete(
    api_key: str,
    model: str,
    system: str,
    user: str,
    timeout_s: float,
    temperature: float = 0.2,
) -> tuple[str, int | None]:
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{quote(model, safe='.-')}:generateContent?key={quote(api_key)}"
    )
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"temperature": temperature, "maxOutputTokens": 512},
    }
    with httpx.Client(timeout=timeout_s) as client:
        response = client.post(url, json=body)
        response.raise_for_status()
        payload = response.json()
    parts = payload.get("candidates") or []
    text = ""
    if parts:
        content = parts[0].get("content") or {}
        for part in content.get("parts") or []:
            text += str(part.get("text") or "")
    usage = payload.get("usageMetadata") or {}
    tokens = usage.get("totalTokenCount")
    if not text.strip():
        raise RuntimeError("empty gemini")
    return text, int(tokens) if tokens is not None else None


def _openai_complete(
    url: str,
    api_key: str,
    model: str,
    system: str,
    user: str,
    timeout_s: float,
    extra_headers: dict[str, str] | None = None,
    temperature: float = 0.2,
) -> tuple[str, int | None]:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": 512,
    }
    with httpx.Client(timeout=timeout_s) as client:
        response = client.post(url, headers=headers, json=body)
        response.raise_for_status()
        payload = response.json()
    choices = payload.get("choices") or []
    text = ""
    if choices:
        text = str((choices[0].get("message") or {}).get("content") or "")
    usage = payload.get("usage") or {}
    tokens = usage.get("total_tokens")
    if not text.strip():
        raise RuntimeError("empty chat completion")
    return text, int(tokens) if tokens is not None else None


@dataclass
class GatewaySettings:
    model_provider: str = "fake"
    google_api_key: str = ""
    gemini_default_model_id: str = ""
    model_secondary_provider: str = ""
    openrouter_api_key: str = ""
    openrouter_model_id: str = ""
    groq_api_key: str = ""
    groq_model_id: str = ""
    model_timeout_s: float = 8.0


def build_gateway(
    settings: GatewaySettings | None = None,
    trace_log: Any | None = None,
) -> ModelGateway:
    cfg = settings or GatewaySettings()
    provider = (cfg.model_provider or "fake").strip().lower()
    if provider in {"", "fake", "none"}:
        return FakeGateway(trace_log=trace_log)
    chain: list[HttpProvider] = []
    order = [provider] + [
        part.strip().lower()
        for part in (cfg.model_secondary_provider or "").split(",")
        if part.strip()
    ]
    seen: set[str] = set()
    for name in order:
        if name in seen:
            continue
        seen.add(name)
        hop = _provider(name, cfg)
        if hop is not None:
            chain.append(hop)
    if not chain:
        return FakeGateway(trace_log=trace_log)
    return FailoverGateway(chain, timeout_s=cfg.model_timeout_s, trace_log=trace_log)


def _provider(name: str, cfg: GatewaySettings) -> HttpProvider | None:
    if name == "gemini" and cfg.google_api_key and cfg.gemini_default_model_id:
        model = cfg.gemini_default_model_id
        key = cfg.google_api_key
        return HttpProvider(
            "gemini",
            lambda system, user, timeout, temperature=0.2: _gemini_complete(
                key, model, system, user, timeout, temperature
            ),
            model_id=model,
        )
    if name == "openrouter" and cfg.openrouter_api_key and cfg.openrouter_model_id:
        model = cfg.openrouter_model_id
        key = cfg.openrouter_api_key
        return HttpProvider(
            "openrouter",
            lambda system, user, timeout, temperature=0.2: _openai_complete(
                "https://openrouter.ai/api/v1/chat/completions",
                key,
                model,
                system,
                user,
                timeout,
                extra_headers={"HTTP-Referer": "https://factory-agent-os.local", "X-Title": "Factory Agent OS"},
                temperature=temperature,
            ),
            model_id=model,
        )
    if name == "groq" and cfg.groq_api_key:
        model = cfg.groq_model_id or "llama-3.3-70b-versatile"
        key = cfg.groq_api_key
        return HttpProvider(
            "groq",
            lambda system, user, timeout, temperature=0.2: _openai_complete(
                "https://api.groq.com/openai/v1/chat/completions",
                key,
                model,
                system,
                user,
                timeout,
                temperature=temperature,
            ),
            model_id=model,
        )
    return None


# Back-compat names for imports/tests that still expect a single-string builder.
def _propose_who_prompt(context: str, text: str, state: WorkingState) -> str:
    system, user = _propose_who_messages(context, text, state)
    return f"{system}\n{user}"


def _propose_prompt(role: str, context: str, text: str) -> str:
    system, user = _propose_messages(role, context, text)
    return f"{system}\n{user}"


def _draft_prompt(role: str, context: str, facts: dict[str, Any], fallback: str) -> str:
    _ = fallback
    system, user = _draft_messages(role, context, facts)
    return f"{system}\n{user}"
