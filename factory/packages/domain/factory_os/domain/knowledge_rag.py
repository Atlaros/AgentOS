"""Token-overlap snippets from a structured shop pack.

No embeddings and no network. A later vector index can wrap
``retrieve_knowledge_snippets`` and keep the same return shape.
"""

from __future__ import annotations

import re
from typing import Any

from factory_os.domain.knowledge import _FAQ_REPLACE, _FAQ_STOP, _one_line
from factory_os.domain.seed import tokenize

_SNIPPET_CHARS = 280
_POLICY_KEYS = ("cancel", "warranty", "claims", "promos", "order_status")
_PROFILE_KEYS = ("summary", "differentiator", "hours", "delivery_zones", "payment")
_PROFILE_LABELS = {
    "hours": "Horario: ",
    "delivery_zones": "Zonas de delivery: ",
    "payment": "Forma de pago: ",
}
_PROFILE_ALIASES = {
    "summary": frozenset({"quienes", "somos", "identidad", "vision", "mision", "nosotros"}),
    "differentiator": frozenset({"quienes", "diferencia", "diferencial", "vision", "destaca"}),
    "hours": frozenset({"horario", "hora", "horas", "abren", "cierran", "atienden"}),
    "delivery_zones": frozenset({"delivery", "envio", "envios", "zona", "zonas"}),
    "payment": frozenset({"pago", "pagar", "qr", "cobro"}),
}
_POLICY_ALIASES = {
    "cancel": frozenset({"cancel", "cancelar", "cancelacion"}),
    "warranty": frozenset({"garantia", "garantias"}),
    "claims": frozenset({"reclamo", "reclamos"}),
    "promos": frozenset({"promo", "promocion", "promos", "descuento", "oferta"}),
    "order_status": frozenset({"pedido", "estado", "seguimiento"}),
    "returns": frozenset({"devolucion", "devoluciones", "cambio", "cambios"}),
    "exchanges": frozenset({"cambio", "cambios", "devolucion", "devoluciones"}),
}
_PAYMENT_CONFIRM = re.compile(
    r"(?i)(?:payment_status|pago\s+confirmad\w*|ya\s+pag(?:ad[oa]|[oó]|aste|amos)"
    r"|recibimos\s+(?:tu\s+)?pago|pago\s+recibido|\bconfirmed\b)"
)
_PRICE_AMOUNT = re.compile(
    r"(?i)(?:(?:bs|bob|usd)\.?\s*\d|\d+(?:[.,]\d{1,2})?\s*(?:bs|bob|usd)\b|\$\s*\d"
    r"|\b(?:cuesta|cuestan|vale|salen|precio)\s*(?:es|de|:)?\s*\d)"
)


def retrieve_knowledge_snippets(pack: dict[str, Any] | None, query: str, *, limit: int = 2) -> list[dict[str, str]]:
    """Top shop snippets for a customer question.

    Score is the count of meaningful token overlap with the snippet text,
    id, and a few aliases, plus the same FAQ bonuses as ``match_faq``.
    Price amounts and payment-confirmation wording are dropped.
    """
    if not isinstance(pack, dict) or limit < 1:
        return []
    tokens = tokenize(query)
    meaningful = tokens - _FAQ_STOP
    if not meaningful:
        return []
    ranked: list[tuple[int, int, dict[str, str]]] = []
    for index, row in enumerate(_candidates(pack, tokens)):
        score = _overlap(meaningful, row["hay"]) + _faq_bonus(row["id"], row["kind"], tokens)
        if score < 1:
            continue
        ranked.append((score, index, {"id": row["id"], "kind": row["kind"], "text": row["text"]}))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in ranked[:limit]]


def _overlap(meaningful: set[str], hay_text: str) -> int:
    hay = tokenize(hay_text) - _FAQ_STOP
    return len(meaningful & hay)


def _faq_bonus(snippet_id: str, kind: str, tokens: set[str]) -> int:
    if kind == "profile" and snippet_id == "delivery_zones" and {"delivery", "envio", "envios"} & tokens:
        return 2
    if kind != "faq":
        return 0
    bonus = 0
    if {"delivery", "envio", "envios"} & tokens and snippet_id == "delivery":
        bonus += 3
    if {"pago", "pagar", "qr"} & tokens and snippet_id == "pay":
        bonus += 3
    if {"tiktok", "live"} & tokens and snippet_id in {"where", "tiktok-buy"}:
        bonus += 2
    if {"cuenta", "link", "perfil", "pagina", "usuario"} & tokens and snippet_id == "where":
        bonus += 3
    return bonus


def _candidates(pack: dict[str, Any], tokens: set[str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    profile = pack.get("profile") if isinstance(pack.get("profile"), dict) else {}
    for key in _PROFILE_KEYS:
        text = _labeled(key, profile.get(key), _PROFILE_LABELS.get(key, ""))
        if text:
            rows.append(_row(key, "profile", text, _PROFILE_ALIASES[key]))
    policies = pack.get("policies") if isinstance(pack.get("policies"), dict) else {}
    for key in _POLICY_KEYS:
        text = _labeled(key, policies.get(key), "")
        if text:
            rows.append(_row(key, "policy", text, _POLICY_ALIASES[key]))
    rows.extend(_return_rows(policies))
    for faq in pack.get("faqs") or []:
        if not isinstance(faq, dict):
            continue
        snippet_id = str(faq.get("id") or "").strip()
        if not snippet_id or snippet_id == _FAQ_REPLACE:
            continue
        if snippet_id == "tiktok-buy" and not ({"tiktok", "live"} & tokens):
            continue
        text = _faq_text(faq)
        if not text:
            continue
        hay = " ".join(
            part
            for part in (
                snippet_id.replace("-", " "),
                str(faq.get("category") or ""),
                str(faq.get("question") or ""),
                str(faq.get("answer") or ""),
            )
            if part
        )
        rows.append({"id": snippet_id, "kind": "faq", "text": text, "hay": hay})
    return rows


def _return_rows(policies: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    custom = policies.get("returns_answer")
    if isinstance(custom, str) and custom.strip():
        text = _safe_text(custom)
        if text:
            rows.append(_row("returns", "policy", text, _POLICY_ALIASES["returns"]))
    else:
        bit = _bool_rule(policies.get("returns"), "devoluciones")
        if bit:
            rows.append(_row("returns", "policy", bit, _POLICY_ALIASES["returns"]))
    exchange = _bool_rule(policies.get("exchanges"), "cambios")
    if isinstance(policies.get("exchanges"), str):
        exchange = _safe_text(policies.get("exchanges"))
    if exchange:
        rows.append(_row("exchanges", "policy", exchange, _POLICY_ALIASES["exchanges"]))
    return rows


def _bool_rule(value: Any, noun: str) -> str:
    if value is False:
        return f"No aceptamos {noun}."
    if value is True:
        return f"Se aceptan {noun}."
    if isinstance(value, str):
        return _safe_text(value)
    return ""


def _faq_text(row: dict[str, Any]) -> str:
    question = " ".join(str(row.get("question") or "").split())
    answer = " ".join(str(row.get("answer") or "").split())
    return _safe_text(" ".join(part for part in (question, answer) if part))


def _labeled(key: str, value: Any, prefix: str) -> str:
    _ = key
    if not isinstance(value, str):
        return ""
    body = " ".join(value.split())
    if not body:
        return ""
    return _safe_text(f"{prefix}{body}")


def _safe_text(value: Any) -> str:
    text = _one_line(value, _SNIPPET_CHARS)
    if not text or _forbidden(text):
        return ""
    return text


def _forbidden(text: str) -> bool:
    return bool(_PAYMENT_CONFIRM.search(text) or _PRICE_AMOUNT.search(text))


def _row(snippet_id: str, kind: str, text: str, aliases: frozenset[str]) -> dict[str, str]:
    alias_text = " ".join(sorted(aliases))
    return {"id": snippet_id, "kind": kind, "text": text, "hay": f"{snippet_id} {alias_text} {text}"}
