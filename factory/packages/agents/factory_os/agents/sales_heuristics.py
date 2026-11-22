"""Commercial fallbacks when the model does not propose (ADR-003 / ADR-004).

These helpers run ONLY for FakeGateway / provider-down NBA. They must never
override a live SalesDecision. Conversational keyword lists here are pytest
scaffolding — not the production seller path.
"""

from __future__ import annotations

from factory_os.domain.catalog import STOP, parse_budget
from factory_os.domain.models import NextAction, WorkingState
from factory_os.domain.seed import normalize, tokenize
from factory_os.harness.model_gateway import heuristic_proposal, is_fuzzy_greet, product_code_tokens

_CONFIRM = (
    "confirmo",
    "lo quiero",
    "la quiero",
    "comprar",
    "cerramos",
    "me llevo",
    "me lo llevo",
    "quiero ese",
    "quiero esa",
    "esa prenda",
    "esa blusa",
    "reservamelo",
    "reservame",
    "procedamos",
    "continuar con",
    "dale",
    "listo",
)
_CONFIRM_NEGATE = (
    "no quiero",
    "no compro",
    "no la quiero",
    "no lo quiero",
    "no confirmo",
    "mas tarde",
    "después",
    "despues",
)
_GREET_TOKENS = frozenset(
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
_GIFT_NEED = frozenset(
    {"regalo", "regalarle", "regalar", "esposa", "esposo", "novia", "cumple", "cumpleanos", "ella"}
)
_CATEGORY = frozenset(
    {
        "blusa",
        "blusas",
        "vestido",
        "vestidos",
        "falda",
        "faldas",
        "jean",
        "jeans",
        "short",
        "shorts",
        "pantalon",
        "pantalones",
        "polera",
        "poleras",
        "top",
        "tops",
        "prenda",
        "prendas",
    }
)
_DETAIL = frozenset(
    {
        "elegante",
        "economico",
        "economica",
        "barato",
        "barata",
        "baratas",
        "baratos",
        "boda",
        "fiesta",
        "oficina",
        "trabajo",
        "crepe",
        "crepre",
        "hilo",
        "seda",
        "corset",
        "midi",
        "codigo",
        "sku",
        "negro",
        "negra",
        "blanco",
        "blanca",
        "blancas",
        "rojo",
        "roja",
        "azul",
        "verde",
        "camel",
        "beige",
        "talla",
        "talle",
        "xs",
        "xl",
        "xxl",
    }
)
_COMPARE = ("compar", "diferencia", "cual me conviene", "cuál me conviene", "o la otra", "entre esas")
_SOFT_INTEREST = ("me gusta esa", "me gusta ese", "la primera", "la segunda", "esa me gusta")

def welcome_for(pack: dict | None = None) -> str:
    """Customer greeting when the model does not draft. Closet wording stays the default."""
    from factory_os.domain.knowledge import item_word, spoken_shop_name

    return (
        f"Hola, soy Adri de {spoken_shop_name(pack)} ✨ Dime qué {item_word(pack)} buscas "
        "(nombre, código del live, ocasión o una descripción) y te armo opciones del catálogo."
    )


WELCOME = welcome_for()
DISCOVERY = (
    "Claro. Para afinar: ¿talla, color, presupuesto aproximado u ocasión "
    "(día, fiesta, trabajo)?"
)
NO_PROMO = (
    "No hay una promoción cargada con ese descuento. No invento ofertas: "
    "si aparece una en el catálogo, te la muestro."
)
NO_PAID = (
    "El pago todavía no está confirmado en el sistema. "
    "Decir 'ya pagué' no alcanza: cuando el banco confirme el QR, seguimos."
)
NO_QR = (
    "Adri no emite QR ni confirma pagos. Cuando haya pedido, Cobros lo hace con el sistema."
)


def is_chitchat(text: str) -> bool:
    tokens = tokenize(text) - STOP
    return not tokens or tokens <= _GREET_TOKENS or is_fuzzy_greet(text)


def is_reset(text: str) -> bool:
    lowered = normalize(text)
    restart = any(word in lowered for word in ("empec", "empez", "emcpec", "reinici", "reset", "de cero"))
    again = any(word in lowered for word in ("de nuevo", "de neuvo", "de cero", "otra vez"))
    return restart and again


def is_paid_claim(lowered: str) -> bool:
    """Customer claims they already paid — used only by FakeGateway / sales NBA fallback."""
    phrases = (
        "ya pague",
        "ya pagué",
        "acabo de pagar",
        "ya transferi",
        "ya transferí",
        "pague el qr",
        "pagué el qr",
        "ya hice el pago",
        "ya pague el",
        "comprobante",
        "te envío el comprobante",
        "te envio el comprobante",
    )
    blob = normalize(lowered)
    return any(p in blob for p in phrases)


def is_support(lowered: str) -> bool:
    return any(word in lowered for word in ("llego", "roto", "reclamo", "incidencia", "ayer"))


def wants_repeat_sale(lowered: str) -> bool:
    return any(word in lowered for word in ("otro", "igual", "mismo", "repetir"))


def is_confirm(lowered: str) -> bool:
    blob = normalize(lowered)
    if any(neg in blob for neg in _CONFIRM_NEGATE):
        return False
    return any(word in blob for word in _CONFIRM)


def is_price_objection(lowered: str) -> bool:
    return any(word in lowered for word in ("caro", "carisimo", "muy caro"))


def is_promo_ask(lowered: str) -> bool:
    return any(word in lowered for word in ("descuento", "promocion", "oferta", "rebaja", "20%"))


def is_thin_need(text: str) -> bool:
    """True when Adri should ask before dumping catalog (gift or category-only)."""
    if product_code_tokens(text):
        return False
    if parse_budget(text) is not None:
        return False
    tokens = tokenize(text) - STOP
    if not tokens:
        return False
    if tokens & _DETAIL:
        return False
    lowered = normalize(text)
    if any(marker in lowered for marker in ("talla ", "talle ", " color ")):
        return False
    if tokens & _GIFT_NEED:
        return True
    return bool(tokens & _CATEGORY)


def is_pay_how(lowered: str) -> bool:
    return "como pago" in lowered


def wants_compare(lowered: str) -> bool:
    return any(word in lowered for word in _COMPARE)


def is_soft_interest(lowered: str) -> bool:
    return any(word in lowered for word in _SOFT_INTEREST)


def next_best_action(state: WorkingState, text: str, pack: dict | None = None) -> tuple[NextAction, str]:
    """Propose the commercial next step when the model did not.

    Does not grant permissions, run tools, or force a rail.
    """
    hinted = heuristic_proposal(state, text)
    if hinted is not None:
        return hinted.action, hinted.skill
    # Exact product/live code is operational — search even without "quiero".
    if product_code_tokens(text):
        return NextAction.SEARCH_CATALOG, "product_recommendation"
    lowered = normalize(text)
    if is_reset(text) or is_chitchat(text):
        return NextAction.ANSWER, "customer_assistance"
    if is_paid_claim(lowered):
        return NextAction.ANSWER, "customer_assistance"
    from factory_os.domain.knowledge import is_shop_question

    if is_shop_question(text, pack=pack):
        return NextAction.ANSWER, "customer_assistance"
    if is_support(lowered):
        if wants_repeat_sale(lowered) and state.considered_variant_sku:
            return NextAction.SEARCH_CATALOG, "customer_assistance"
        return NextAction.ASK_DISCOVERY_QUESTION, "customer_assistance"
    if state.considered_variant_sku and "al carrito" in lowered and not is_confirm(lowered):
        return NextAction.ADD_TO_CART, "sales_closing"
    if state.considered_variant_sku and (is_confirm(lowered) or is_pay_how(lowered)):
        return NextAction.CREATE_ORDER, "sales_closing"
    if is_pay_how(lowered):
        return NextAction.ANSWER, "sales_closing"
    if parse_budget(text) is not None:
        return NextAction.SEARCH_CATALOG, "product_recommendation"
    if is_promo_ask(lowered) and not is_price_objection(lowered):
        return NextAction.ANSWER, "objection_handling"
    if is_price_objection(lowered):
        return NextAction.HANDLE_OBJECTION, "objection_handling"
    if wants_compare(lowered) and state.last_hits:
        return NextAction.COMPARE, "product_recommendation"
    if is_soft_interest(lowered) and state.considered_variant_sku and not is_confirm(lowered):
        return NextAction.REQUEST_CONFIRMATION, "sales_closing"
    if "recomend" in lowered:
        return NextAction.RECOMMEND, "product_recommendation"
    if is_thin_need(text) and not state.discovery_asked:
        return NextAction.ASK_DISCOVERY_QUESTION, "sales_discovery"
    return NextAction.SEARCH_CATALOG, "product_recommendation"
