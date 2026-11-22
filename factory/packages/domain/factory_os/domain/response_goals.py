"""Closed response_goal codes for SalesDecision.

The model returns a code. The runtime translates it to a fixed Spanish phrase
before Adri drafts. Unknown free text becomes empty so regional wording cannot
leak into the draft.
"""

from __future__ import annotations

RESPONSE_GOALS: tuple[tuple[str, str], ...] = (
    ("greet", "saludá breve y hacé una sola pregunta sobre qué busca"),
    (
        "ask_detail",
        "una sola pregunta para afinar (talla, color, presupuesto u ocasión), sin listar todo junto",
    ),
    (
        "recommend_ask_fit",
        "recomendá una opción concreta del FACTS y preguntá talla o color",
    ),
    (
        "clarify_payment",
        "explicá que el pago es por QR y que el chat no confirma el pago",
    ),
    (
        "handle_price_objection",
        "ofrecé alternativa real del catálogo o preguntá presupuesto, sin inventar descuento",
    ),
    ("show_options", "mostrá hasta 3 opciones con precio de FACTS y pedí que elija"),
    (
        "confirm_intent",
        "confirmá que quiere esa prenda antes de pasar a cobro, una sola pregunta",
    ),
    ("restart", "reconocé que quiere empezar de cero, saludá y preguntá qué busca"),
    (
        "shop_faq",
        "respondé la duda de la tienda con hechos de la ficha, en tu estilo, sin pegar un reglamento",
    ),
)

RESPONSE_GOAL_PHRASES: dict[str, str] = dict(RESPONSE_GOALS)
RESPONSE_GOAL_CODES: frozenset[str] = frozenset(RESPONSE_GOAL_PHRASES)


def normalize_response_goal(raw: str) -> str:
    """Return a known code, or empty when the text is not one."""
    code = str(raw or "").strip()
    if code in RESPONSE_GOAL_CODES:
        return code
    folded = code.lower()
    if folded in RESPONSE_GOAL_CODES:
        return folded
    return ""


def phrase_for_response_goal(code: str) -> str:
    """Spanish phrase for a known code. Empty when the code is unknown."""
    return RESPONSE_GOAL_PHRASES.get(normalize_response_goal(code), "")
