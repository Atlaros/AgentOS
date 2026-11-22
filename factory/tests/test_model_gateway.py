from factory_os.domain.models import NextAction, WorkingState
from factory_os.harness.model_gateway import (
    DraftResult,
    FakeGateway,
    FailoverGateway,
    GatewaySettings,
    HttpProvider,
    _draft_prompt,
    build_gateway,
    draft_echoes_fallback,
    draft_is_catalog_list,
    grounded_draft,
    heuristic_proposal,
    parse_proposal,
    product_code_tokens,
    render_reply,
)


def test_fake_gateway_is_default() -> None:
    assert isinstance(build_gateway(GatewaySettings()), FakeGateway)
    assert isinstance(build_gateway(GatewaySettings(model_provider="gemini")), FakeGateway)


def test_heuristic_hol_is_greeting() -> None:
    proposal = heuristic_proposal(WorkingState(), "hol")
    assert proposal is not None
    assert proposal.action is NextAction.ANSWER


def test_heuristic_pago1_is_close() -> None:
    proposal = heuristic_proposal(WorkingState(), "quiero la blusa pago1")
    assert proposal is not None
    assert proposal.action is NextAction.CREATE_ORDER
    assert proposal.arguments.get("codigo") == "pago1"


def test_heuristic_pago_spaced_is_close() -> None:
    proposal = heuristic_proposal(WorkingState(), "quiero la blusa pago 1")
    assert proposal is not None
    assert proposal.action is NextAction.CREATE_ORDER
    assert proposal.arguments.get("codigo") == "pago1"
    assert product_code_tokens("código h 001 porfa") == ["h001"]


def test_heuristic_browse_is_not_close() -> None:
    assert heuristic_proposal(WorkingState(), "quiero una blusa de seda") is None


def test_parse_proposal_json() -> None:
    parsed = parse_proposal('{"action":"search_catalog","skill":"product_recommendation"}', "gemini")
    assert parsed is not None
    assert parsed.action is NextAction.SEARCH_CATALOG
    assert parsed.provider == "gemini"


def test_parse_proposal_coerces_invented_skill() -> None:
    invented = parse_proposal('{"action":"search_catalog","skill":"product_search"}', "gemini")
    assert invented is not None
    assert invented.skill == "product_recommendation"
    unknown = parse_proposal('{"action":"create_order","skill":"whatever"}', "gemini")
    assert unknown is not None
    assert unknown.skill == "sales_closing"
    mismatched = parse_proposal('{"action":"create_order","skill":"customer_assistance"}', "gemini")
    assert mismatched is not None
    assert mismatched.skill == "sales_closing"


def test_parse_proposal_tool_infers_action() -> None:
    search = parse_proposal(
        '{"tool":"catalog.search","arguments":{"query":"blusas 1 bs"}}',
        "gemini",
    )
    assert search is not None
    assert search.action is NextAction.SEARCH_CATALOG
    assert search.skill == "product_recommendation"
    assert search.arguments["query"] == "blusas 1 bs"
    assert search.arguments["tool"] == "catalog.search"
    close = parse_proposal('{"tool":"order.create","arguments":{"codigo":"pago1"}}', "gemini")
    assert close is not None
    assert close.action is NextAction.CREATE_ORDER
    assert close.skill == "sales_closing"
    qr = parse_proposal('{"tool":"payment.create_qr"}', "gemini")
    assert qr is not None
    assert qr.action is NextAction.ANSWER


def test_grounded_draft_drops_prompt_leak() -> None:
    facts = {
        "hits": [{"product_sku": "h001", "price": "145.00", "currency": "BOB", "stock": 1}],
        "fallback": "Pedido creado: blusa de hilo por 145.00 BOB.",
    }
    leak = (
        "We need to produce a response in Spanish. ONLY with these facts. "
        "No invent price. We have facts: product_sku h001 price 145.00 BOB stock 1"
    )
    assert grounded_draft(leak, facts, facts["fallback"]) == facts["fallback"]


def test_first_turn_greeting_allowed() -> None:
    """Test 1 — no prior Adri reply: greeting is allowed."""
    context = "recent:\n  customer: hola"
    fallback = "Hola, soy Adri de Closet. Decime qué prenda buscás."
    draft = "¡Hola! ¿Cómo estás? Soy Adri de Closet. Decime qué prenda buscás."
    facts = {"hits": [], "fallback": fallback}
    assert grounded_draft(draft, facts, fallback, context=context) == draft


def test_followup_rejects_regreeting() -> None:
    """Test 2 — Adri already spoke: draft must not open with a greeting."""
    context = (
        "recent:\n"
        "  customer: hola\n"
        "  Adri: Hola, soy Adri de Closet. Decime qué prenda buscás...\n"
        "  customer: estoy bsucnado blusas"
    )
    fallback = (
        "Encontré esto en el catálogo:\n"
        "- blusa de seda · 160.00 BOB · código s018\n"
        "Si te cierra, escribí 'confirmo' o 'me llevo ese' y armo el pedido."
    )
    facts = {
        "hits": [
            {"product_sku": "s018", "codigo": "s018", "price": "160.00", "currency": "BOB", "stock": 1},
            {"product_sku": "s013", "codigo": "s013", "price": "160.00", "currency": "BOB", "stock": 1},
            {"product_sku": "s001", "codigo": "s001", "price": "135.00", "currency": "BOB", "stock": 1},
        ],
        "fallback": fallback,
    }
    bad = (
        "¡Hola! ¿Cómo estás? Te cuento que encontré estas opciones de blusas en el catálogo: "
        "blusa de seda s018 a 160.00 BOB."
    )
    spoken = grounded_draft(bad, facts, fallback, context=context)
    assert not spoken.lower().startswith("¡hola")
    assert "160.00" in spoken
    assert "código s018" not in spoken.lower()


def test_search_draft_keeps_catalog_facts() -> None:
    """Test 3 — may list hits; must not invent different price/SKU/stock."""
    context = (
        "recent:\n"
        "  customer: hola\n"
        "  Adri: Hola, soy Adri...\n"
        "  customer: estoy bsucnado blusas"
    )
    fallback = "Encontré s018, s013 y s001."
    facts = {
        "hits": [
            {"product_sku": "s018", "codigo": "s018", "price": "160.00", "currency": "BOB", "stock": 1, "name": "blusa de seda"},
            {"product_sku": "s013", "codigo": "s013", "price": "160.00", "currency": "BOB", "stock": 1, "name": "blusa de seda"},
            {"product_sku": "s001", "codigo": "s001", "price": "135.00", "currency": "BOB", "stock": 1, "name": "top multi formas"},
        ],
        "fallback": fallback,
    }
    ok = (
        "Encontré blusa de seda s018 a 160.00 BOB (stock 1), "
        "s013 a 160.00 BOB, y top multi formas s001 a 135.00 BOB."
    )
    assert grounded_draft(ok, facts, fallback, context=context) == ok
    assert grounded_draft(
        "Encontré s018 a 999.00 BOB.",
        facts,
        fallback,
        context=context,
    ) == fallback


def test_draft_rejects_automatic_cta() -> None:
    """Test 4 — LLM must not introduce confirmo / me llevo ese CTA."""
    context = (
        "recent:\n"
        "  customer: hola\n"
        "  Adri: Hola, soy Adri...\n"
        "  customer: estoy bsucnado blusas"
    )
    fallback = (
        "Encontré s018 a 160.00 BOB.\n"
        "Si te cierra, escribí 'confirmo' o 'me llevo ese' y armo el pedido."
    )
    facts = {
        "hits": [{"product_sku": "s018", "codigo": "s018", "price": "160.00", "currency": "BOB", "stock": 1}],
        "fallback": fallback,
    }
    with_cta = (
        "Encontré blusa s018 a 160.00 BOB. "
        "Si alguna te gusta, avisame con un 'confirmo' o 'me llevo ese' y te armo el pedido."
    )
    assert grounded_draft(with_cta, facts, fallback, context=context) == fallback


def test_grounding_still_rejects_false_product_claims() -> None:
    """Test 5 — false price/SKU still rejected."""
    facts = {
        "hits": [{"product_sku": "s018", "codigo": "s018", "price": "160.00", "currency": "BOB", "stock": 1}],
        "fallback": "Encontré s018 a 160.00 BOB.",
    }
    assert grounded_draft("La blusa AC-FAKE-001 sale 10.00 BOB", facts, facts["fallback"]) == facts["fallback"]
    assert grounded_draft("s018 está 160.00 BOB", facts, facts["fallback"]).startswith("s018")


def test_grounding_rejects_invented_price() -> None:
    facts = {"hits": [{"price": "1.00", "codigo": "pago1", "product_sku": "pago1", "variant_sku": "pago1-U-B", "stock": 50}]}
    assert grounded_draft("La blusa pago1 sale 999.00 BOB", facts, "fallback") == "fallback"
    assert "1.00" in grounded_draft("La blusa pago1 sale 1.00 BOB", facts, "fallback")


def test_grounding_rejects_promo_payment_warranty_and_stock() -> None:
    facts = {
        "hits": [{"price": "145.00", "codigo": "h001", "product_sku": "h001", "stock": 1}],
        "fallback": "Encontré h001 a 145.00 BOB, stock 1.",
    }
    safe = "La prenda h001 está 145 BOB, stock 1."
    assert grounded_draft(safe, facts, "fallback") == safe
    assert grounded_draft("Hay 20% de descuento en h001", facts, "fallback") == "fallback"
    assert grounded_draft("Hay descuento y envio gratis", facts, "fallback") == "fallback"
    assert grounded_draft("El pago está confirmado por el banco", facts, "fallback") == "fallback"
    assert grounded_draft("Tiene garantía y te devolvemos el dinero", facts, "fallback") == "fallback"
    assert grounded_draft("Quedan 99 unidades de h001", facts, "fallback") == "fallback"


def test_grounding_allows_denied_promo_and_confirmed_payment_from_facts() -> None:
    denied = "No hay descuento inventado. El precio de h001 es 145.00 BOB."
    facts = {"hits": [{"price": "145.00", "codigo": "h001", "stock": 1}], "fallback": denied}
    assert grounded_draft(denied, facts, denied) == denied
    paid_facts = {
        "hits": [{"price": "1.00", "codigo": "pago1", "stock": 50}],
        "payment_status": "confirmed",
        "fallback": "Pago confirmado por el sistema.",
    }
    paid = "Pago confirmado por el sistema. El ítem pago1 salió 1.00 BOB."
    assert grounded_draft(paid, paid_facts, paid_facts["fallback"]) == paid


def test_render_reply_drops_paid_claim_while_pending() -> None:
    class Lie:
        def propose(self, **_kwargs):
            return None

        def draft(self, *, fallback: str, **_kwargs):
            return DraftResult(text="El pago está confirmado por el banco.", provider="script")

    pending = render_reply(
        Lie(),
        role="cobros",
        context="",
        fallback="El pago sigue pendiente en el sistema.",
        facts={"payment_status": "pending"},
    )
    assert "pendiente" in pending.lower()
    assert "confirmado por el banco" not in pending.lower()

    allowed = render_reply(
        Lie(),
        role="cobros",
        context="",
        fallback="Pago confirmado por el sistema.",
        facts={"payment_status": "confirmed"},
    )
    assert "confirmado por el banco" in allowed.lower()


def test_failover_uses_second_provider() -> None:
    def boom(_system: str, _user: str, _timeout: float, _temperature: float = 0.2) -> tuple[str, int | None]:
        raise RuntimeError("down")

    def ok(_system: str, _user: str, _timeout: float, _temperature: float = 0.2) -> tuple[str, int | None]:
        return '{"action":"answer","skill":"customer_assistance"}', 12

    gateway = FailoverGateway(
        [HttpProvider("gemini", boom), HttpProvider("groq", ok)],
        timeout_s=1,
    )
    proposal = gateway.propose(role="sales", context="", text="hola", state=WorkingState())
    assert proposal is not None
    assert proposal.provider == "groq"
    assert gateway.last_event["fallback"] == "gemini"
    assert gateway.last_event["tokens"] == 12


def test_draft_echo_and_catalog_list_detectors() -> None:
    script = "Hola, soy Adri de Authentic Closet. Dime qué prenda buscas."
    assert draft_echoes_fallback(script, script)
    assert draft_echoes_fallback(script + " ✨", script)
    assert not draft_echoes_fallback("Hola, ¿qué prenda tenés en mente hoy?", script)
    listed = "- Blusa de hilo · 140 BOB\n- Blusa corset · 145 BOB"
    assert draft_is_catalog_list(listed)
    assert not draft_is_catalog_list("La de hilo camel está 140 BOB, código rh001. ¿Te va esa talla?")


def test_draft_prompt_forbids_copying_the_script() -> None:
    prompt = _draft_prompt("sales", "recent:", {"response_goal": "preguntar talla"}, "Claro. Para afinar.")
    assert "Respondé ÚNICAMENTE con el mensaje final" in prompt
    assert "viñetas" in prompt
    assert "preguntar talla" in prompt
    assert "Borrador (no lo leas" not in prompt
    assert "Claro. Para afinar." not in prompt


def test_draft_retries_when_the_model_copies_the_script() -> None:
    script = "Claro. Para afinar: ¿talla, color, presupuesto aproximado u ocasión?"
    calls: list[float] = []

    def complete(_system: str, _user: str, _timeout: float, temperature: float = 0.2) -> tuple[str, int | None]:
        calls.append(temperature)
        if len(calls) == 1:
            return script, 4
        return "¿Qué talla usás normalmente?", 6

    gateway = FailoverGateway([HttpProvider("gemini", complete, model_id="gemini-test")], timeout_s=1)
    result = gateway.draft(role="sales", context="", facts={}, fallback=script)
    assert calls == [0.45, 0.45]
    assert result.used_fallback is False
    assert result.text == "¿Qué talla usás normalmente?"
    assert "Para afinar" not in result.text
