"""Adri sales employee — LLM proposes; runtime authorizes and executes (ADR-003/004).

Heuristics live in `sales_heuristics` and are fallback only. ConversationStage is
commercial context for the model; business step is WorkingState.graph_node.
"""

from __future__ import annotations

from uuid import UUID

from factory_os.agents.sales_heuristics import (
    DISCOVERY,
    NO_PAID,
    NO_PROMO,
    NO_QR,
    is_chitchat,
    is_paid_claim,
    is_pay_how,
    is_price_objection,
    is_promo_ask,
    is_reset,
    is_support,
    is_thin_need,
    next_best_action,
    welcome_for,
)
from factory_os.contracts.employees import Identity
from factory_os.domain.catalog import parse_budget
from factory_os.domain.models import Conversation, ConversationStage, EmployeeRole, HandoffFolder, NextAction, WorkingState
from factory_os.domain.response_goals import phrase_for_response_goal
from factory_os.domain.seed import normalize
from factory_os.harness.context import compile_context
from factory_os.harness.model_gateway import (
    FRIENDLY_IDLE_REOPEN,
    FakeGateway,
    ModelGateway,
    heuristic_proposal,
    product_code_tokens,
    render_reply,
)
from factory_os.harness.tools import ToolRuntime, run_tool

# Re-export for tests and FakeGateway callers that import from sales.
__all__ = [
    "apply_stage",
    "authorize_create_order",
    "authorize_discovery",
    "catalog_search_payload",
    "handle_sales",
    "is_chitchat",
    "is_reset",
    "next_best_action",
    "order_bound_to_shown",
    "reset_working_state",
]

# Bounded commercial READ loop per turn (ADR-003 / T8).
MAX_READ_STEPS = 2


def _shop_pack(store, tenant_id):
    """Card for customer fallbacks. Missing card keeps item_word / shop_label defaults."""
    from factory_os.domain.knowledge import pack_for_tenant

    return pack_for_tenant(store, tenant_id)


def _draft_knowledge(pack, tenant_id, text: str, extra: dict | None = None) -> dict:
    """Answer FACTS: short shop snippets. They never carry a price or a paid flag."""
    from factory_os.domain.knowledge import is_shop_question, shop_pack_for
    from factory_os.domain.knowledge_rag import retrieve_knowledge_snippets

    source = pack if isinstance(pack, dict) else shop_pack_for(tenant_id)
    facts = dict(extra or {})
    if isinstance(source, dict):
        snippets = retrieve_knowledge_snippets(source, text)
        if snippets:
            facts["knowledge_hits"] = snippets
    goal = facts.get("response_goal")
    if not (isinstance(goal, str) and goal.strip()) and is_shop_question(text, tenant_id, source):
        facts["response_goal"] = "shop_faq"
    return facts


def _item_noun(store, tenant_id) -> str:
    from factory_os.domain.knowledge import item_word

    return item_word(_shop_pack(store, tenant_id))


def _item_plural(store, tenant_id) -> str:
    from factory_os.domain.knowledge import item_plural

    return item_plural(_shop_pack(store, tenant_id))
_POST_READ_ACTIONS = frozenset(
    {
        NextAction.RECOMMEND,
        NextAction.COMPARE,
        NextAction.REQUEST_CONFIRMATION,
        NextAction.ANSWER,
        NextAction.HANDLE_OBJECTION,
        NextAction.ASK_DISCOVERY_QUESTION,
    }
)


def _payment_status_reply(
    runtime: ToolRuntime,
    identity: Identity,
    conversation: Conversation,
    store=None,
) -> tuple[str, dict]:
    """READ payment.status; never marks paid from customer text (ADR-004)."""
    from factory_os.domain.models import PaymentStatus

    if conversation.state.order_id is None:
        noun = _item_noun(store, identity.tenant_id)
        return (
            "Todavía no hay pedido, así que no hay un pago que confirmar. "
            f"Cuando elijamos la {noun} y armes el pedido, Cobros te pasa el QR.",
            {"payment_status": "none"},
        )
    if not conversation.state.provider_ref:
        conversation.state.pass_to(
            EmployeeRole.COBROS,
            from_role=EmployeeRole.SALES,
            pending="issue_qr",
            reason="paid_claim_no_qr",
            payment_state="pending",
        )
        return (
            "Hay pedido, pero todavía no hay QR. Te paso con Cobros para emitirlo. "
            "El chat no marca el pago como confirmado.",
            {"payment_status": "pending"},
        )
    status = run_tool(
        runtime,
        identity,
        conversation,
        "payment.status",
        {"provider_ref": conversation.state.provider_ref},
    )
    if status.get("status") == PaymentStatus.CONFIRMED.value:
        conversation.state.pass_to(
            EmployeeRole.OPS,
            from_role=EmployeeRole.SALES,
            pending="collect_address",
            reason="payment_confirmed",
            payment_state="confirmed",
        )
        return (
            "El sistema ya confirma el pago. Te paso con Operaciones para el envío.",
            {"payment_status": "confirmed"},
        )
    conversation.state.pass_to(
        EmployeeRole.COBROS,
        from_role=EmployeeRole.SALES,
        pending="wait_adapter",
        reason="paid_claim_pending",
        payment_state="pending",
    )
    return (NO_PAID, {"payment_status": "pending"})


def reset_working_state(state: WorkingState) -> None:
    state.considered_variant_sku = None
    state.last_hits = []
    state.order_id = None
    state.payment_id = None
    state.provider_ref = None
    state.last_employee = None
    state.folder = HandoffFolder()
    state.needs_human = False
    state.human_takeover = False
    state.stage = ConversationStage.NEW
    state.customer_need = None
    state.current_objection = None
    state.last_action = None
    state.last_skill = None
    state.pending_action = None
    state.discovery_asked = False
    state.budget_max = None
    state.size = None
    state.color = None
    state.occasion = None
    state.style = None
    state.preference_provenance = {}
    state.cart = []
    state.incident = None
    state.graph_node = None
    state.chat_resolution = ""


def order_bound_to_shown(state: WorkingState, text: str) -> bool:
    """Operational bind: named catalog code or a variant already shown this chat.

    Does NOT parse conversational magic words — the LLM decides the customer wants it.
    """
    if product_code_tokens(text):
        return True
    sku = state.considered_variant_sku
    if not sku:
        return False
    shown = {str(hit.get("variant_sku") or "") for hit in state.last_hits}
    return (not shown) or (sku in shown)


def authorize_create_order(action: NextAction, state: WorkingState, text: str) -> tuple[NextAction, str | None]:
    """Runtime only checks there is something to sell — not how the client phrased it.

    LLM proposes CREATE_ORDER; keywords never force a close (ADR-003).
    """
    if action is not NextAction.CREATE_ORDER:
        return action, None
    if order_bound_to_shown(state, text):
        return action, "sales_closing"
    return NextAction.SEARCH_CATALOG, "product_recommendation"


def authorize_discovery(
    action: NextAction,
    state: WorkingState,
    text: str,
    *,
    from_sales_decision: bool = False,
) -> tuple[NextAction, str | None]:
    """Thin-need guard for heuristic/NBA path only.

    When a SalesDecision already chose SEARCH/RECOMMEND/COMPARE, do not replace it
    (ADR-003). FakeGateway builds its decision via next_best_action, so gift and
    category-only still ask first under MODEL_PROVIDER=fake.
    """
    if from_sales_decision:
        return action, None
    if state.discovery_asked or not is_thin_need(text):
        return action, None
    if action in {
        NextAction.SEARCH_CATALOG,
        NextAction.RECOMMEND,
        NextAction.COMPARE,
    }:
        return NextAction.ASK_DISCOVERY_QUESTION, "sales_discovery"
    return action, None


def _hit_price(hit: dict) -> float:
    try:
        return float(hit.get("price") or 0)
    except (TypeError, ValueError):
        return 0.0


def bind_shown_from_args(state: WorkingState, args: dict) -> None:
    """LLM may pick a shown SKU; runtime ignores SKUs that were never listed."""
    needle = str(args.get("variant_sku") or args.get("codigo") or "").strip()
    if not needle:
        return
    hit = _match_hit(state.last_hits, needle)
    if hit:
        state.considered_variant_sku = hit["variant_sku"]


def apply_proposed_tool(
    action: NextAction,
    skill: str,
    args: dict,
    text: str,
    *,
    from_sales_decision: bool = False,
) -> tuple[NextAction, str]:
    """Map LLM tool names onto NBA actions. Permission still happens at execute.

    When from_sales_decision=True, do not apply conversational dictionaries
    (shop FAQ token overlap, thin-need, budget-as-objection). Only operational maps.
    """
    tool = str(args.get("tool") or "").strip()
    if tool == "payment.create_qr":
        return NextAction.ANSWER, "customer_assistance"
    if tool == "cart.remove":
        return NextAction.ADD_TO_CART, "sales_closing"
    if tool == "cart.add":
        return NextAction.ADD_TO_CART, "sales_closing"
    if tool == "order.create":
        return NextAction.CREATE_ORDER, "sales_closing"
    if from_sales_decision:
        if tool == "catalog.search" and action in {
            NextAction.ANSWER,
            NextAction.ASK_DISCOVERY_QUESTION,
        }:
            return NextAction.SEARCH_CATALOG, "product_recommendation"
        return action, skill
    # --- Fallback path only (no live SalesDecision) ---
    # Do not remap via is_shop_question here — FakeGateway/NBA already chose ANSWER.
    if parse_budget(text) is not None and action in {
        NextAction.HANDLE_OBJECTION,
        NextAction.ANSWER,
        NextAction.ASK_DISCOVERY_QUESTION,
    }:
        return NextAction.SEARCH_CATALOG, "product_recommendation"
    if action is NextAction.ASK_DISCOVERY_QUESTION and not is_thin_need(text):
        return NextAction.SEARCH_CATALOG, "product_recommendation"
    if tool == "catalog.search" and action in {
        NextAction.ANSWER,
        NextAction.ASK_DISCOVERY_QUESTION,
    }:
        return NextAction.SEARCH_CATALOG, "product_recommendation"
    return action, skill


def search_query(state: WorkingState, text: str, args: dict, turn_prefs: dict | None = None) -> str:
    """Prefer the LLM/Fake tool query; otherwise the client text. No keyword rewrite."""
    from factory_os.domain.sales_decision import preference_search_hints

    _ = state
    query = str(args.get("query") or "").strip() or text
    if parse_budget(text) is not None and parse_budget(query) is None:
        query = f"{query} {text}".strip()
    hints = preference_search_hints(state, turn_prefs)
    if hints and hints.lower() not in query.lower():
        query = f"{query} {hints}".strip()
    return query


def catalog_search_payload(
    state: WorkingState,
    text: str,
    args: dict,
    turn_prefs: dict | None = None,
) -> dict:
    """Build catalog.search args from SalesDecision + durable prefs (T9)."""
    local = turn_prefs or {}
    query = search_query(state, text, args, turn_prefs)
    filters: dict[str, str] = {}
    raw_filters = args.get("filters")
    if isinstance(raw_filters, dict):
        for key, value in raw_filters.items():
            if value:
                filters[str(key)] = str(value)
    for key in ("size", "color", "occasion", "style", "category"):
        value = args.get(key) or local.get(key) or getattr(state, key, None)
        if value and key not in filters:
            filters[key] = str(value)
    talla = args.get("talla")
    if talla and "size" not in filters:
        filters["size"] = str(talla)
    budget = args.get("budget_max") or local.get("budget_max") or state.budget_max
    if budget is None:
        budget = parse_budget(text) or parse_budget(query)
    payload: dict = {"query": query}
    if budget is not None:
        payload["budget_max"] = str(budget)
    if filters:
        payload["filters"] = filters
    return payload


def apply_stage(state: WorkingState, action: NextAction, text: str) -> None:
    """Write ConversationStage from the authorized action (LLM context, not graph_node)."""
    lowered = normalize(text)
    if action is NextAction.ASK_DISCOVERY_QUESTION:
        state.stage = ConversationStage.POST_SALE if is_support(lowered) else ConversationStage.DISCOVERY
    elif action is NextAction.COMPARE:
        state.stage = ConversationStage.CONSIDERATION
    elif action is NextAction.REQUEST_CONFIRMATION:
        state.stage = ConversationStage.READY_TO_BUY
    elif action is NextAction.HANDLE_OBJECTION:
        state.stage = ConversationStage.OBJECTION
    elif action is NextAction.RECOMMEND:
        state.stage = ConversationStage.RECOMMENDATION
    elif action is NextAction.SEARCH_CATALOG:
        if state.customer_need or state.discovery_asked:
            state.stage = ConversationStage.NEED_IDENTIFIED
    elif action is NextAction.CREATE_ORDER:
        state.stage = ConversationStage.CHECKOUT
    elif action is NextAction.ADD_TO_CART:
        state.stage = ConversationStage.CONSIDERATION
    elif action is NextAction.ANSWER and (is_promo_ask(lowered) or is_price_objection(lowered)):
        state.stage = ConversationStage.OBJECTION


def stage_after_catalog(state: WorkingState, hits: list[dict]) -> None:
    """Finalize stage after catalog.search (hits vs miss). Overrides apply_stage SEARCH."""
    if hits:
        state.stage = ConversationStage.RECOMMENDATION
    elif state.customer_need:
        state.stage = ConversationStage.NEED_IDENTIFIED
    else:
        state.stage = ConversationStage.DISCOVERY


def _format_hits(
    hits: list[dict],
    *,
    highlight_sku: str | None = None,
    ask: str | None = None,
    named_codes: set[str] | None = None,
    store=None,
    tenant_id=None,
) -> str:
    """≤3 options; highlight one; soft advance question — no internal jargon (T10/T12)."""
    shown = hits[:3]
    if not shown:
        noun = _item_noun(store, tenant_id)
        return (
            f"No encontré esa {noun} en el catálogo. "
            "¿Me das un nombre o una descripción un poco más concreta?"
        )
    lines = ["Encontré estas opciones:"]
    highlight = highlight_sku or shown[0].get("variant_sku")
    for hit in shown:
        extra = " · ".join(
            part
            for part in (
                f"talla {hit['talla']}" if hit.get("talla") else "",
                str(hit.get("color") or "").strip(),
            )
            if part
        )
        detail = f" · {extra}" if extra else ""
        mark = " ← te la destaco" if hit.get("variant_sku") == highlight else ""
        codigo = str(hit.get("codigo") or "").strip()
        named = {code.lower() for code in (named_codes or set())}
        code_bit = f" · código {codigo}" if codigo and codigo.lower() in named else ""
        lines.append(
            f"- {hit['name']}{detail} · {hit['price']} {hit['currency']} · stock {hit['stock']}"
            f"{code_bit}{mark}"
        )
    lines.append(ask or "¿Cuál te gusta más, o afinamos talla o color?")
    return "\n".join(lines)


_SEND_IMAGE_MODEL_KEYS = frozenset(
    {
        "url",
        "link",
        "path",
        "image_url",
        "caption",
        "image_path",
        "media_url",
        "href",
        "src",
        "filename",
        "content",
        "bytes",
        "wa_number",
        "conversation_id",
        "human_takeover",
        "sent_product_skus",
    }
)


def _turn_sent_product_images(state: WorkingState) -> list[str]:
    raw = getattr(state, "_sent_product_images", None)
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    return []


def _record_sent_product_image(state: WorkingState, product_sku: str) -> None:
    sku = product_sku.strip()
    if not sku:
        return
    sent = _turn_sent_product_images(state)
    if sku not in sent:
        sent.append(sku)
    state._sent_product_images = sent  # type: ignore[attr-defined]


def send_product_image_payload(
    conversation: Conversation,
    *,
    wa_number: str,
    raw_args: dict | None = None,
) -> dict:
    """Trusted runtime fields only; strip model URL/path/caption/wa_number."""
    args = dict(raw_args or {})
    product_sku = str(args.get("product_sku") or "").strip()
    return {
        "product_sku": product_sku,
        "wa_number": wa_number,
        "conversation_id": str(conversation.id),
        "human_takeover": bool(conversation.state.human_takeover),
        "sent_product_skus": _turn_sent_product_images(conversation.state),
    }


def _send_product_image(
    runtime: ToolRuntime,
    identity: Identity,
    conversation: Conversation,
    *,
    wa_number: str,
    raw_args: dict | None = None,
    trace=None,
) -> dict:
    """Execute send_product_image with runtime-injected identity; never trust LLM media keys."""
    from factory_os.harness.policy import PolicyDenied

    # Rebuild from product_sku only — never forward model url/path/caption/wa_number.
    raw = {
        k: v
        for k, v in dict(raw_args or {}).items()
        if str(k).strip().lower() not in _SEND_IMAGE_MODEL_KEYS
    }
    body = send_product_image_payload(conversation, wa_number=wa_number, raw_args=raw)
    try:
        result = run_tool(
            runtime,
            identity,
            conversation,
            "send_product_image",
            body,
        )
    except PolicyDenied as exc:
        if trace is not None:
            trace.record(
                "tool_read",
                parsed_action="send_product_image",
                payload={"tool": "send_product_image", "error": exc.code, "product_sku": body.get("product_sku")},
            )
        return {"ok": False, "error": exc.code, "message": str(exc)}
    if result.get("ok"):
        _record_sent_product_image(conversation.state, str(body.get("product_sku") or ""))
    if trace is not None:
        trace.record(
            "tool_read",
            parsed_action="send_product_image",
            payload={
                "tool": "send_product_image",
                "product_sku": body.get("product_sku"),
                "ok": bool(result.get("ok")),
                "error": result.get("error"),
                "source": "catalog_media",
            },
        )
    return result


def _search(
    runtime: ToolRuntime,
    identity: Identity,
    conversation: Conversation,
    query: str,
    *,
    payload: dict | None = None,
    highlight_sku: str | None = None,
    trace=None,
    store=None,
) -> str:
    body = dict(payload) if payload else {"query": query}
    if "query" not in body:
        body["query"] = query
    result = run_tool(runtime, identity, conversation, "catalog.search", body)
    hits = result.get("hits") or []
    if trace is not None:
        facts = [
            {
                "codigo": h.get("codigo"),
                "name": h.get("name"),
                "price": h.get("price"),
                "stock": h.get("stock"),
                "variant_sku": h.get("variant_sku"),
            }
            for h in (hits or [])[:3]
        ]
        trace.record(
            "tool_read",
            parsed_action="catalog.search",
            payload={
                "tool": "catalog.search",
                "arguments": {k: body[k] for k in body if k in {"query", "budget_max", "filters", "codigo"}},
                "hit_count": len(hits or []),
                "facts": facts,
                "source": "postgres_catalog",
            },
        )
    if not hits:
        conversation.state.considered_variant_sku = None
        conversation.state.last_hits = []
        stage_after_catalog(conversation.state, [])
        noun = _item_noun(store, identity.tenant_id)
        return (
            f"No encontré esa {noun} en el catálogo. "
            "¿Me das un nombre o una descripción un poco más concreta?"
        )

    conversation.state.last_hits = hits[:3]
    pick = highlight_sku
    if pick and not any(h.get("variant_sku") == pick for h in conversation.state.last_hits):
        pick = None
    conversation.state.considered_variant_sku = pick or hits[0]["variant_sku"]
    stage_after_catalog(conversation.state, conversation.state.last_hits)
    return _format_hits(
        hits,
        highlight_sku=conversation.state.considered_variant_sku,
        named_codes=set(product_code_tokens(str(body.get("query") or query))),
        store=store,
        tenant_id=identity.tenant_id,
    )


def _compare(conversation: Conversation, store=None) -> str:
    hits = conversation.state.last_hits[:3]
    if len(hits) < 2:
        if hits:
            return _format_hits(hits, store=store, tenant_id=conversation.tenant_id)
        plural = _item_plural(store, conversation.tenant_id)
        return (
            f"Todavía no tengo dos {plural} para comparar. "
            "Dime qué buscas y armo opciones del catálogo."
        )
    lines = ["Comparo con lo que hay en catálogo:"]
    for hit in hits:
        lines.append(
            f"- {hit['name']} · {hit['price']} {hit['currency']} · stock {hit['stock']}"
        )
    lines.append("¿Con cuál te quedas, o miramos otra?")
    return "\n".join(lines)


def _request_confirmation(conversation: Conversation, store=None) -> str:
    hits = conversation.state.last_hits
    sku = conversation.state.considered_variant_sku
    hit = next((item for item in hits if item.get("variant_sku") == sku), hits[0] if hits else None)
    if hit is None:
        noun = _item_noun(store, conversation.tenant_id)
        return (
            f"Cuando veas una {noun} del catálogo, dime y te confirmo precio y stock "
            "antes de armar el pedido."
        )
    return (
        f"{hit['name']} está {hit['price']} {hit['currency']} (stock {hit['stock']}). "
        "Si te cierra, escribe 'confirmo' y armo el pedido."
    )


def _handle_objection(
    runtime: ToolRuntime,
    identity: Identity,
    conversation: Conversation,
    text: str,
    *,
    turn_prefs: dict | None = None,
    args: dict | None = None,
    store=None,
) -> str:
    conversation.state.current_objection = "price"
    payload = catalog_search_payload(conversation.state, text, args or {}, turn_prefs)
    if parse_budget(text) is not None or payload.get("budget_max"):
        return _search(runtime, identity, conversation, payload["query"], payload=payload, store=store)
    shown = list(conversation.state.last_hits)
    if not shown:
        noun = _item_noun(store, identity.tenant_id)
        return (
            f"No invento descuentos. Si me dices la {noun}, busco en el catálogo "
            "el precio real y, si hay, una alternativa más accesible."
        )
    ceiling = shown[0]["price"]
    alt_payload = dict(payload)
    alt_payload["query"] = f"{shown[0].get('name') or ''} {ceiling} bs".strip()
    _search(runtime, identity, conversation, alt_payload["query"], payload=alt_payload, store=store)
    cheaper = [hit for hit in conversation.state.last_hits if _hit_price(hit) < _hit_price(shown[0])]
    conversation.state.stage = ConversationStage.OBJECTION
    if cheaper:
        conversation.state.last_hits = cheaper[:3]
        conversation.state.considered_variant_sku = cheaper[0]["variant_sku"]
        listed = _format_hits(cheaper, store=store, tenant_id=identity.tenant_id)
        return (
            f"El precio de {shown[0]['name']} es {shown[0]['price']} {shown[0]['currency']}; "
            "no hay un descuento inventado. "
            f"Si el presupuesto aprieta, estas son opciones reales más accesibles:\n{listed}"
        )
    conversation.state.last_hits = shown
    conversation.state.considered_variant_sku = shown[0].get("variant_sku")
    cheaper_shown = sorted(shown, key=_hit_price)[0]
    return (
        f"El precio de {shown[0]['name']} es {shown[0]['price']} {shown[0]['currency']}; "
        "no hay un descuento inventado. "
        f"Si el presupuesto aprieta, una opción real es {cheaper_shown['name']} "
        f"a {cheaper_shown['price']} {cheaper_shown['currency']} (stock {cheaper_shown['stock']}). "
        "Dime si seguimos con alguna o buscamos otra."
    )


def _match_hit(hits: list[dict], needle: str) -> dict | None:
    from factory_os.domain.seed import tokenize

    wanted = normalize(needle)
    if not wanted:
        return None
    for hit in hits:
        for key in ("codigo", "product_sku", "variant_sku"):
            if normalize(str(hit.get(key) or "")) == wanted:
                return hit
        if wanted in tokenize(str(hit.get("name") or "")):
            return hit
    return None


def _resolve_considered(runtime: ToolRuntime, identity: Identity, conversation: Conversation, text: str) -> None:
    codes = product_code_tokens(text)
    for query in codes:
        result = run_tool(runtime, identity, conversation, "catalog.search", {"query": query})
        hits = result.get("hits") or []
        hit = _match_hit(hits, query) or (hits[0] if hits else None)
        if hit:
            conversation.state.last_hits = hits[:3]
            conversation.state.considered_variant_sku = hit["variant_sku"]
            return
    if conversation.state.considered_variant_sku:
        return
    if conversation.state.last_hits:
        conversation.state.considered_variant_sku = conversation.state.last_hits[0].get("variant_sku")


def _cart_summary(cart: list, store=None, tenant_id=None) -> str:
    from factory_os.domain.cart_quote import format_line, quote_lines

    if not cart:
        return "El carrito está vacío."
    quote = quote_lines(cart)
    rows = [format_line(line) for line in quote.lines]
    if quote.discount:
        noun = _item_noun(store, tenant_id)
        plural = _item_plural(store, tenant_id)
        rows.append(
            f"Con {quote.garment_count} {plural} el descuento es "
            f"{quote.discount_each} {quote.currency} por {noun} "
            f"(-{quote.discount} {quote.currency})."
        )
    rows.append(f"Total si paga ahora: {quote.total} {quote.currency}.")
    return "\n".join(rows)


def _reissue_if_unpaid(conversation: Conversation) -> bool:
    """A live unpaid QR is stale once the cart changes. Cobros mints another."""
    if not (conversation.state.provider_ref or conversation.state.payment_id):
        return False
    conversation.state.provider_ref = None
    conversation.state.payment_id = None
    conversation.state.pass_to(
        EmployeeRole.COBROS,
        from_role=EmployeeRole.SALES,
        pending="issue_qr",
        reason="cart_changed",
        payment_state="pending",
    )
    return True


def _add_to_cart(
    runtime: ToolRuntime,
    identity: Identity,
    conversation: Conversation,
    text: str,
    *,
    remove: bool,
    store=None,
) -> str:
    noun = _item_noun(store, identity.tenant_id)
    sku = conversation.state.considered_variant_sku
    if not remove:
        _resolve_considered(runtime, identity, conversation, text)
        sku = conversation.state.considered_variant_sku
    if not sku:
        return f"Decime cuál {noun} sumamos al carrito."
    tool = "cart.remove" if remove else "cart.add"
    changed = run_tool(
        runtime,
        identity,
        conversation,
        tool,
        {"variant_sku": sku, "quantity": 1, "cart": conversation.state.cart},
    )
    if changed.get("error"):
        if remove:
            return f"Esa {noun} no está en el carrito."
        return f"No pude agregar ese artículo al carrito. ¿Quieres que busquemos otra {noun}?"
    conversation.state.cart = changed["cart"]
    summary = _cart_summary(conversation.state.cart, store, identity.tenant_id)
    if _reissue_if_unpaid(conversation):
        return f"Actualicé el carrito.\n{summary}\nTe paso con Cobros para el QR del total nuevo."
    if remove:
        return f"La saqué del carrito.\n{summary}"
    return (
        f"Quedó en el carrito, sin cobrar todavía.\n{summary}\n"
        "Cuando quieras pagar, armo un solo QR por el total."
    )


def _create_order(
    runtime: ToolRuntime,
    identity: Identity,
    conversation: Conversation,
    customer_id: UUID,
    text: str,
    store=None,
) -> str:
    _ = customer_id
    _resolve_considered(runtime, identity, conversation, text)
    sku = conversation.state.considered_variant_sku
    if not sku:
        return _search(runtime, identity, conversation, text, store=store)
    if not order_bound_to_shown(conversation.state, text):
        return _request_confirmation(conversation, store=store)
    already = {str(item.get("variant_sku") or "") for item in conversation.state.cart}
    item: dict = {}
    if sku not in already:
        added = run_tool(
            runtime,
            identity,
            conversation,
            "cart.add",
            {"variant_sku": sku, "quantity": 1, "cart": conversation.state.cart},
        )
        if added.get("error"):
            noun = _item_noun(store, identity.tenant_id)
            return f"No pude agregar ese artículo al carrito. ¿Quieres que busquemos otra {noun}?"
        conversation.state.cart = added["cart"]
        item = added.get("item") or {}
    else:
        item = next(
            (row for row in conversation.state.cart if str(row.get("variant_sku") or "") == sku),
            {},
        )
    conversation.state.pass_to(
        EmployeeRole.COBROS,
        from_role=EmployeeRole.SALES,
        pending="issue_qr",
        reason="checkout_ready",
        payment_state="pending",
    )
    conversation.state.stage = ConversationStage.CHECKOUT
    conversation.state.last_action = NextAction.HANDOFF.value
    codigo = ""
    for hit in conversation.state.last_hits:
        if hit.get("variant_sku") == sku:
            codigo = str(hit.get("codigo") or "")
            break
    code_bit = f"código {codigo}" if codigo else f"código {item.get('product_sku') or sku}"
    return (
        f"{_cart_summary(conversation.state.cart, store, identity.tenant_id)}\n"
        f"Te paso con Cobros para el QR ({code_bit}). "
        "Queda en reserva hasta que el banco confirme; ahí pasa a pedido."
    )


def _facts(conversation: Conversation, extra: dict | None = None) -> dict:
    payload = {"hits": list(conversation.state.last_hits), "fallback": ""}
    if extra:
        payload.update(extra)
    raw_goal = payload.get("response_goal")
    if isinstance(raw_goal, str) and raw_goal.strip():
        phrase = phrase_for_response_goal(raw_goal)
        if phrase:
            payload["response_goal"] = phrase
        else:
            del payload["response_goal"]
    elif "response_goal" in payload:
        del payload["response_goal"]
    return payload


def _speak(
    gateway: ModelGateway,
    identity: Identity,
    conversation: Conversation,
    fallback: str,
    extra: dict | None = None,
    store=None,
) -> str:
    facts = _facts(conversation, extra)
    return render_reply(
        gateway,
        role=identity.role.value,
        context=compile_context(identity, conversation, store=store),
        fallback=fallback,
        facts=facts,
    )


def _resolve_proposal(
    desk: ModelGateway,
    identity: Identity,
    conversation: Conversation,
    text: str,
    store,
):
    """Authorize WHAT: LLM/Fake propose → tools/discovery/close guards."""
    hinted = heuristic_proposal(conversation.state, text)
    from factory_os.domain.playbook import (
        PLAYBOOK_MAX_HITS,
        format_playbook_hints,
        search_playbook,
    )

    playbook_hits = search_playbook(text, limit=PLAYBOOK_MAX_HITS)
    playbook_extra = format_playbook_hints(playbook_hits)
    rag_extra = ""
    if store is not None:
        from factory_os.domain.catalog import format_product_rag, search_catalog

        try:
            rag_hits = search_catalog(store, identity.tenant_id, text, limit=5)
            rag_extra = format_product_rag(rag_hits)
        except Exception:
            rag_extra = ""
    parts = [p for p in (text, playbook_extra, rag_extra) if p]
    propose_extra = "\n".join(parts)
    proposed = desk.propose(
        role=identity.role.value,
        context=compile_context(identity, conversation, extra=propose_extra, store=store),
        text=text,
        state=conversation.state,
    )
    last_event = getattr(desk, "last_event", {}) or {}
    network_provider = str(last_event.get("provider") or "")
    propose_parse_success = bool(last_event.get("parsed")) and network_provider not in {
        "",
        "none",
        "heuristic",
    }
    has_sales_decision = proposed is not None and (
        proposed.decision is not None or (propose_parse_success and network_provider not in {"", "none"})
    )

    heuristic_overridden = False
    proposal_args = dict(proposed.arguments) if proposed is not None else {}
    turn_prefs: dict = {}
    # Live path: never override the model with keyword heuristics (ADR-003).
    # FakeGateway / provider-down already baked heuristics into `proposed`.
    if has_sales_decision and proposed is not None:
        action, skill = proposed.action, proposed.skill
        if network_provider not in {"", "fake", "none", "heuristic"}:
            decision_source = "llm_propose"
        else:
            decision_source = "sales_decision"
        heuristic_overridden = hinted is not None
        if proposed.decision is not None:
            from factory_os.domain.sales_decision import apply_preference_patch

            turn_prefs = apply_preference_patch(conversation.state, proposed.decision.preference_patch)
    elif proposed is not None:
        action, skill = proposed.action, proposed.skill
        decision_source = "heuristic"
    else:
        action, skill = next_best_action(conversation.state, text)
        decision_source = "nba_fallback"
        heuristic_overridden = hinted is not None

    from_sd = decision_source in {"sales_decision", "llm_propose"}
    action, skill = apply_proposed_tool(
        action, skill, proposal_args, text, from_sales_decision=from_sd
    )
    bind_shown_from_args(conversation.state, proposal_args)
    action, discovery_skill = authorize_discovery(
        action, conversation.state, text, from_sales_decision=from_sd
    )
    if discovery_skill:
        skill = discovery_skill
    action, authorized_skill = authorize_create_order(action, conversation.state, text)
    if authorized_skill:
        skill = authorized_skill

    # Stash playbook + override flag on proposed for trace via a small side channel.
    meta = {
        "heuristic_overridden": heuristic_overridden,
        "playbook_hits": playbook_hits,
        "last_event": last_event,
        "propose_parse_success": propose_parse_success,
        "network_provider": network_provider,
    }
    return action, skill, decision_source, proposal_args, turn_prefs, hinted, proposed, from_sd, meta


def handle_sales(
    identity: Identity,
    runtime: ToolRuntime,
    conversation: Conversation,
    customer_id: UUID,
    text: str,
    gateway: ModelGateway | None = None,
    store=None,
) -> str:
    from factory_os.harness.agent_trace import snapshot_working_state

    desk = gateway or FakeGateway()
    trace = getattr(desk, "trace_log", None)

    if store is not None:
        prefs = store.get_customer_preferences(identity.tenant_id, customer_id)
        for key, value in prefs.items():
            if key == "budget_max" and conversation.state.budget_max is None:
                from decimal import Decimal, InvalidOperation

                try:
                    conversation.state.budget_max = Decimal(value)
                    conversation.state.preference_provenance["budget_max"] = "customer_explicit"
                except (InvalidOperation, ValueError):
                    pass
            elif key in {"size", "color", "occasion", "style"} and not getattr(
                conversation.state, key, None
            ):
                setattr(conversation.state, key, value)
                conversation.state.preference_provenance[key] = "customer_explicit"

    from factory_os.domain.learning import note_live_or_organic

    note_live_or_organic(conversation, text)

    state_before = snapshot_working_state(conversation.state)
    if trace is not None:
        trace.record(
            "state_before",
            payload={"state": state_before, "client_text": text},
        )

    if conversation.turn_idle_reopen:
        conversation.state.last_action = NextAction.ANSWER.value
        conversation.state.last_skill = "customer_assistance"
        reply = _speak(
            desk,
            identity,
            conversation,
            FRIENDLY_IDLE_REOPEN,
            {"idle_reopen": True},
            store=store,
        )
        _trace_state_after(trace, conversation, reply)
        return reply

    (
        action,
        skill,
        decision_source,
        proposal_args,
        turn_prefs,
        hinted,
        proposed,
        from_sd,
        meta,
    ) = _resolve_proposal(desk, identity, conversation, text, store)

    conversation.state.last_action = action.value
    conversation.state.last_skill = skill
    raw_date = str(proposal_args.get("fulfill_on") or "").strip()
    if raw_date:
        conversation.state.fulfill_on = raw_date[:10]
    apply_stage(conversation.state, action, text)

    last_event = meta["last_event"]
    propose_parse_success = meta["propose_parse_success"]
    network_provider = meta["network_provider"]
    playbook_hits = meta["playbook_hits"]
    heuristic_overridden = meta["heuristic_overridden"]

    if trace is not None:
        decision_payload = {
            "heuristic_proposal": (
                {"action": hinted.action.value, "skill": hinted.skill, "provider": hinted.provider}
                if hinted
                else None
            ),
            "propose_result": (
                {
                    "action": proposed.action.value,
                    "skill": proposed.skill,
                    "provider": proposed.provider,
                }
                if proposed
                else None
            ),
            "propose_parse_success": propose_parse_success,
            "decision_source": decision_source,
            "heuristic_overridden": heuristic_overridden,
            "final_action": action.value,
            "final_skill": skill,
            "client_text": text,
            "tool": proposal_args.get("tool"),
            "proposal_arguments": proposal_args,
            "turn_prefs": turn_prefs,
            "playbook_hits": [hit.as_dict() for hit in playbook_hits],
            "propose_used_fallback": bool(last_event.get("used_fallback")),
            "parse_success": propose_parse_success,
        }
        if proposed is not None and proposed.decision is not None:
            decision_payload["sales_decision"] = {
                "understanding": proposed.decision.understanding,
                "response_goal": proposed.decision.response_goal,
                "preference_patch": proposed.decision.preference_patch.as_dict(),
            }
        trace.record(
            "sales_decision",
            parsed_action=action.value,
            parsed_skill=skill,
            provider=last_event.get("provider"),
            model=last_event.get("model"),
            used_fallback=bool(last_event.get("used_fallback")),
            payload=decision_payload,
        )

    response_goal = ""
    if proposed is not None and proposed.decision is not None:
        response_goal = proposed.decision.response_goal

    pack = _shop_pack(store, identity.tenant_id)
    noun = _item_noun(store, identity.tenant_id)

    if is_reset(text):
        reset_working_state(conversation.state)
        conversation.state.last_action = NextAction.ANSWER.value
        conversation.state.last_skill = "customer_assistance"
        reply = _speak(
            desk,
            identity,
            conversation,
            welcome_for(pack),
            {"response_goal": "restart"},
            store=store,
        )
        _trace_state_after(trace, conversation, reply)
        return reply

    if action is NextAction.ADD_TO_CART:
        remove = str(proposal_args.get("tool") or "") == "cart.remove"
        reply = _speak(
            desk,
            identity,
            conversation,
            _add_to_cart(runtime, identity, conversation, text, remove=remove, store=store),
            {"response_goal": response_goal} if response_goal else None,
            store=store,
        )
        _trace_state_after(trace, conversation, reply)
        return reply

    if action is NextAction.CREATE_ORDER:
        reply = _speak(
            desk,
            identity,
            conversation,
            _create_order(runtime, identity, conversation, customer_id, text, store=store),
            {"response_goal": response_goal, "mention_code": True}
            if response_goal
            else {"mention_code": True},
            store=store,
        )
        _trace_state_after(trace, conversation, reply)
        return reply

    if str(proposal_args.get("tool") or "") == "send_product_image":
        wa_number = ""
        if store is not None:
            customer = store.get_customer(identity.tenant_id, customer_id)
            if customer is not None:
                wa_number = customer.wa_number
        conversation.state.last_skill = skill if skill in {
            "product_recommendation",
            "customer_assistance",
        } else "product_recommendation"
        img = _send_product_image(
            runtime,
            identity,
            conversation,
            wa_number=wa_number,
            raw_args=proposal_args,
            trace=trace,
        )
        product_sku = str(proposal_args.get("product_sku") or "").strip()
        if product_sku:
            fallback = _search(
                runtime,
                identity,
                conversation,
                product_sku,
                highlight_sku=None,
                trace=trace,
                store=store,
            )
        else:
            fallback = str(img.get("message") or img.get("caption") or "")
        if img.get("ok") and img.get("caption"):
            # Image already delivered on the channel; keep text grounded on store facts.
            fallback = fallback or str(img.get("caption"))
        elif img.get("error") == "no_image":
            fallback = str(img.get("message") or fallback)
        elif img.get("error") and not fallback:
            fallback = "No pude mandar la foto ahora. ¿Seguimos con otra prenda del catálogo?"
        reply = _speak(
            desk,
            identity,
            conversation,
            fallback,
            {"response_goal": response_goal or "recommend_ask_fit", "image_sent": bool(img.get("ok"))},
            store=store,
        )
        _trace_state_after(trace, conversation, reply)
        return reply

    if action is NextAction.ASK_DISCOVERY_QUESTION:
        conversation.state.customer_need = conversation.state.customer_need or text
        conversation.state.discovery_asked = True
        if is_support(normalize(text)):
            reply = _speak(
                desk,
                identity,
                conversation,
                "Anoto lo del pedido anterior: eso es postventa (reclamo o seguimiento), "
                "no lo resuelvo inventando una política. Adri puede armarte un pedido nuevo: "
                f"¿cuál {noun} quieres repetir (nombre o código)?",
                store=store,
            )
            _trace_state_after(trace, conversation, reply)
            return reply
        reply = _speak(
            desk,
            identity,
            conversation,
            DISCOVERY,
            {
                "response_goal": response_goal or "ask_detail"
            },
            store=store,
        )
        _trace_state_after(trace, conversation, reply)
        return reply

    if decision_source != "llm_propose":
        from factory_os.domain.knowledge import is_shop_question

        if is_shop_question(text, identity.tenant_id, pack):
            action = NextAction.ANSWER
            skill = "customer_assistance"
            # The proposal may still carry catalog.search from before the shop card was read.
            if str(proposal_args.get("tool") or "") == "catalog.search":
                proposal_args.pop("tool", None)

    if action is NextAction.ANSWER and str(proposal_args.get("tool") or "") != "catalog.search":
        if str(proposal_args.get("tool") or "") == "payment.create_qr":
            reply = _speak(
                desk,
                identity,
                conversation,
                NO_QR,
                _draft_knowledge(pack, identity.tenant_id, text),
                store=store,
            )
            _trace_state_after(trace, conversation, reply)
            return reply
        if is_paid_claim(normalize(text)):
            fallback, facts = _payment_status_reply(runtime, identity, conversation, store=store)
            reply = _speak(
                desk,
                identity,
                conversation,
                fallback,
                _draft_knowledge(pack, identity.tenant_id, text, facts),
                store=store,
            )
            _trace_state_after(trace, conversation, reply)
            return reply
        if is_pay_how(normalize(text)):
            from factory_os.domain.knowledge import item_word

            reply = _speak(
                desk,
                identity,
                conversation,
                f"Cuando confirmemos el {item_word(pack)} armo el pedido y Cobros te pasa el QR. El chat no confirma el pago.",
                _draft_knowledge(pack, identity.tenant_id, text),
                store=store,
            )
            _trace_state_after(trace, conversation, reply)
            return reply
        if is_promo_ask(normalize(text)):
            reply = _speak(
                desk,
                identity,
                conversation,
                NO_PROMO,
                _draft_knowledge(pack, identity.tenant_id, text),
                store=store,
            )
            _trace_state_after(trace, conversation, reply)
            return reply
        # Keyword FAQ only for Fake / provider-down — never after a live LLM propose (ADR-003).
        if decision_source != "llm_propose":
            from factory_os.domain.knowledge import shop_reply

            known = shop_reply(text, identity.tenant_id, pack)
            if known:
                reply = _speak(
                    desk,
                    identity,
                    conversation,
                    known,
                    _draft_knowledge(
                        pack,
                        identity.tenant_id,
                        text,
                        {"policy_ok": True, "shop": True},
                    ),
                    store=store,
                )
                _trace_state_after(trace, conversation, reply)
                return reply
        closing_goal = response_goal or "greet"
        if not response_goal:
            from factory_os.domain.knowledge import is_shop_question, shop_pack_for

            source = pack if isinstance(pack, dict) else shop_pack_for(identity.tenant_id)
            if is_shop_question(text, identity.tenant_id, source):
                closing_goal = "shop_faq"
        reply = _speak(
            desk,
            identity,
            conversation,
            welcome_for(pack),
            _draft_knowledge(
                pack,
                identity.tenant_id,
                text,
                {"response_goal": closing_goal},
            ),
            store=store,
        )
        _trace_state_after(trace, conversation, reply)
        return reply

    # --- READ loop (T8): decide → catalog.search → optional re-decide → draft ---
    read_steps = 0
    fallback = ""
    highlight = str(proposal_args.get("variant_sku") or proposal_args.get("highlight") or "").strip() or None

    if action is NextAction.HANDLE_OBJECTION:
        fallback = _handle_objection(
            runtime,
            identity,
            conversation,
            text,
            turn_prefs=turn_prefs,
            args=proposal_args,
            store=store,
        )
        read_steps = 1
    elif action is NextAction.COMPARE and conversation.state.last_hits:
        fallback = _compare(conversation, store=store)
    elif action is NextAction.REQUEST_CONFIRMATION and conversation.state.last_hits:
        fallback = _request_confirmation(conversation, store=store)
    else:
        payload = catalog_search_payload(conversation.state, text, proposal_args, turn_prefs)
        if is_support(normalize(text)) and conversation.state.considered_variant_sku:
            prefix = "Anoto lo del pedido anterior (postventa). Para repetir la compra, esto hay en catálogo:\n"
            fallback = prefix + _search(
                runtime,
                identity,
                conversation,
                conversation.state.considered_variant_sku,
                highlight_sku=highlight,
                trace=trace,
                store=store,
            )
        else:
            fallback = _search(
                runtime,
                identity,
                conversation,
                payload["query"],
                payload=payload,
                highlight_sku=highlight,
                trace=trace,
                store=store,
            )
        read_steps = 1

        if (
            from_sd
            and read_steps < MAX_READ_STEPS
            and network_provider not in {"", "fake", "none", "heuristic"}
            and conversation.state.last_hits
        ):
            import json

            facts_blob = json.dumps(
                {"hits": conversation.state.last_hits[:3], "response_goal": response_goal},
                ensure_ascii=False,
            )
            second = desk.propose(
                role=identity.role.value,
                context=compile_context(
                    identity, conversation, extra=f"read_facts={facts_blob}", store=store
                ),
                text=text,
                state=conversation.state,
            )
            if second is not None and second.action in _POST_READ_ACTIONS:
                action, skill = second.action, second.skill
                if second.decision is not None and second.decision.response_goal:
                    response_goal = second.decision.response_goal
                conversation.state.last_action = action.value
                conversation.state.last_skill = skill
                apply_stage(conversation.state, action, text)
                if action is NextAction.COMPARE:
                    fallback = _compare(conversation, store=store)
                elif action is NextAction.REQUEST_CONFIRMATION:
                    fallback = _request_confirmation(conversation, store=store)
                elif action is NextAction.RECOMMEND:
                    pick = str((second.arguments or {}).get("variant_sku") or "").strip() or highlight
                    fallback = _format_hits(
                        conversation.state.last_hits,
                        highlight_sku=pick or conversation.state.considered_variant_sku,
                        store=store,
                        tenant_id=identity.tenant_id,
                    )
                read_steps = 2
                if trace is not None:
                    trace.record(
                        "sales_decision_after_read",
                        parsed_action=action.value,
                        parsed_skill=skill,
                        provider=getattr(desk, "last_event", {}).get("provider"),
                        payload={"read_steps": read_steps, "response_goal": response_goal},
                    )

    if action is NextAction.REQUEST_CONFIRMATION and not fallback:
        fallback = _request_confirmation(conversation, store=store)
    if action is NextAction.COMPARE and not fallback:
        fallback = _compare(conversation, store=store)

    extra = {"response_goal": response_goal, "read_steps": read_steps}
    reply = _speak(desk, identity, conversation, fallback, extra, store=store)
    if trace is not None and read_steps:
        for event in reversed(getattr(trace, "events", [])):
            if event.operation == "sales_decision":
                event.payload["read_steps"] = read_steps
                break
    _trace_state_after(trace, conversation, reply)
    return reply


def _trace_state_after(trace, conversation: Conversation, reply: str) -> None:
    if trace is None:
        return
    from factory_os.harness.agent_trace import snapshot_working_state

    last_draft = None
    for event in reversed(getattr(trace, "events", [])):
        if event.operation == "draft":
            last_draft = event
            break
    payload: dict = {"state": snapshot_working_state(conversation.state), "final_response": reply}
    if last_draft is not None:
        payload["draft_payload"] = last_draft.payload
        payload["grounding_ok"] = last_draft.payload.get("grounding_ok")
        payload["used_fallback"] = last_draft.used_fallback
    trace.record(
        "state_after",
        used_fallback=last_draft.used_fallback if last_draft else None,
        payload=payload,
    )
