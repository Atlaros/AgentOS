"""Draft path: system/user, leak detector, soft fallback (never bullet catalog)."""

from uuid import uuid4

from factory_os.domain.models import HandoffFolder, WorkingState
from factory_os.harness.model_gateway import (
    DRAFT_SYSTEM,
    FRIENDLY_DISCOVERY,
    FRIENDLY_WELCOME,
    _draft_messages,
    _propose_messages,
    _propose_who_messages,
    draft_leaks_prompt,
    grounded_draft,
    soft_draft_fallback,
)


LEAK_SAMPLES = [
    "We need to output a short (2-4 sentences) response in Spanish of Bolivia...",
    "Si en recent ya hay una respuesta de Adri, no saludes de nuevo.",
    "Borrador (no lo leas en voz alta): - p001 Chaqueta denim ...",
    "- p001 Chaqueta denim Bs120\n- b001 Blusa Bs80",
]


def test_leak_detector_catches_known_patterns() -> None:
    for text in LEAK_SAMPLES:
        assert draft_leaks_prompt(text), text


def test_soft_fallback_never_starts_with_bullet() -> None:
    soft = soft_draft_fallback(
        context="recent:\n  Adri: Hola",
        facts={},
        operational="Encontré estas opciones:\n- a\n- b",
    )
    assert not soft.strip().startswith(("-", "•"))
    assert soft == FRIENDLY_DISCOVERY


def test_soft_fallback_with_hits_is_prose() -> None:
    soft = soft_draft_fallback(
        context="recent:",
        facts={
            "hits": [
                {
                    "name": "Blusa crepé manga corta",
                    "price": "1.00",
                    "currency": "BOB",
                    "codigo": "p001",
                }
            ]
        },
    )
    assert "Blusa crepé" in soft
    assert "p001" not in soft
    assert "código" not in soft.lower()
    assert not soft.strip().startswith("-")
    assert "Encontré estas opciones" not in soft
    assert "le late" not in soft.lower()
    assert soft.endswith("¿Te sirve esa o afinamos talla o color?")


def test_soft_fallback_does_not_dump_knowledge_hits() -> None:
    soft = soft_draft_fallback(
        context="recent:",
        facts={
            "knowledge_hits": [
                {"id": "delivery", "kind": "faq", "text": "Sí, hacemos delivery a todo Bolivia."},
                {"id": "summary", "kind": "profile", "text": "Tienda digital de ropa femenina."},
            ]
        },
    )
    assert soft == FRIENDLY_WELCOME
    assert not soft.strip().startswith(("-", "•", "*"))
    assert "delivery" not in soft.lower()
    assert "bolivia" not in soft.lower()


def test_grounded_draft_falls_back_on_leak() -> None:
    result = grounded_draft(
        "We need to explain that Adri already greeted the customer...",
        {"hits": []},
        "Encontré estas opciones:\n- x",
        context="recent:\n  Adri: Hola",
    )
    assert result == FRIENDLY_DISCOVERY
    assert "we need to" not in result.lower()


def test_grounded_draft_happy_path_prose() -> None:
    prose = "La blusa crepé está a 1.00 BOB (código p001). ¿Te late?"
    facts = {
        "hits": [
            {"name": "Blusa crepé", "price": "1.00", "currency": "BOB", "codigo": "p001"}
        ],
        "fallback": prose,
    }
    result = grounded_draft(
        prose,
        facts,
        "Encontré estas opciones:\n- Blusa",
        context="recent:\n  Adri: Hola\n  customer: busco una blusa",
    )
    assert "blusa crepé" in result.lower()
    assert "1.00" in result
    assert "p001" not in result.lower()


def test_grounded_draft_keeps_code_at_payment_and_when_client_said_it() -> None:
    prose = "La blusa crepé está a 1.00 BOB (código p001). ¿Te late?"
    facts = {
        "hits": [
            {"name": "Blusa crepé", "price": "1.00", "currency": "BOB", "codigo": "p001"}
        ],
        "mention_code": True,
    }
    paid = grounded_draft(prose, facts, prose, context="recent:\n  customer: esa")
    assert "p001" in paid.lower()
    echoed = grounded_draft(
        prose,
        {**facts, "mention_code": False},
        prose,
        context="recent:\n  customer: el código del live es p001",
    )
    assert "p001" in echoed.lower()


def test_welcome_when_cold() -> None:
    soft = soft_draft_fallback(context="recent:", facts={})
    assert soft == FRIENDLY_WELCOME


def test_safety_net_and_prompts_read_compiled_shop_card() -> None:
    context = "shop=Ferretería Norte\nitem=artículo\nrecent:"
    soft = soft_draft_fallback(context=context, facts={})
    assert "Ferretería Norte" in soft
    assert "artículo" in soft
    assert "Authentic Closet" not in soft
    assert "prenda" not in soft.lower()

    draft_system, _draft_user = _draft_messages("sales", context, {})
    assert "Ferretería Norte" in draft_system
    assert "artículo" in draft_system
    assert "Authentic Closet" not in draft_system

    who_system, _who_user = _propose_who_messages(context, "hola", WorkingState())
    assert "Ferretería Norte" in who_system
    assert "Authentic Closet" not in who_system


def test_sales_decision_prompt_reads_shop_and_item() -> None:
    context = "shop=Ferretería Norte\nitem=artículo\nrecent:"
    system, _user = _propose_messages("sales", context, "hola")
    assert "Sos Adri, vendedora de Ferretería Norte." in system
    assert "otro artículo" in system
    assert "un artículo" in system
    assert "1–3 artículos" in system or "1-3 artículos" in system
    assert "prenda" not in system.lower()
    assert "blusas, vestidos, faldas" in system
    assert "No inventes precio, stock, SKU ni pago." in system


def test_sales_decision_prompt_is_priority_table_with_goal_codes() -> None:
    system, _user = _propose_messages("sales", "recent:", "hola")
    assert "Prioridad" in system
    assert "situación" in system
    for code in (
        "greet",
        "ask_detail",
        "recommend_ask_fit",
        "clarify_payment",
        "handle_price_objection",
        "show_options",
        "confirm_intent",
        "restart",
        "shop_faq",
    ):
        assert code in system
    assert "payment.create_qr" in system
    assert "No inventes precio, stock, SKU ni pago." in system
    assert '"tone"' not in system
    assert "cordial" not in system
    assert "le late" not in system.lower()
    assert "no un simple ok de acuse" in system


def test_sales_decision_prompt_keeps_closet_wording() -> None:
    bare, _bare_user = _propose_messages("sales", "recent:", "hola")
    named, _named_user = _propose_messages(
        "sales", "shop=Authentic Closet\nitem=prenda\nrecent:", "hola"
    )
    shop_only, _shop_user = _propose_messages(
        "sales", "shop=Authentic Closet\nrecent:", "hola"
    )
    assert bare == named == shop_only
    assert "Sos el vendedor digital" in bare
    assert "otra prenda" in bare


def test_sales_decision_prompt_keeps_prenda_when_item_missing() -> None:
    context = "shop=Ferretería Norte\nrecent:"
    system, _user = _propose_messages("sales", context, "hola")
    assert "vendedora de Ferretería Norte" in system
    assert "otra prenda" in system


def test_closet_draft_without_brand_lines_stays_on_draft_system() -> None:
    bare, _bare_user = _draft_messages("sales", "recent:", {})
    named, _named_user = _draft_messages(
        "sales", "shop=Authentic Closet\nitem=prenda\nrecent:", {}
    )
    voice_only, _voice_user = _draft_messages(
        "sales",
        "shop=Authentic Closet\nitem=prenda\nvoice=tú emojis=moderate\nrecent:",
        {},
    )
    assert bare == named == voice_only == DRAFT_SYSTEM
    assert "IDENTIDAD" not in named
    assert "Cuando uses una FAQ" not in named


def test_brand_crumbs_enter_draft_system_without_vision() -> None:
    vision = "Una visión larga de la tienda que no debe entrar al prompt. " * 12
    context = "\n".join(
        [
            "shop=Ferretería Norte",
            "item=artículo",
            "identity=Ferretería de barrio, atención directa",
            "tone=directa",
            "traits=clara, breve, concreta",
            "words_use=listo, dale",
            "words_avoid=barato, gratis",
            "examples=Te lo dejo separado|Está en 50 bolivianos hoy",
            f"vision={vision}",
            "recent:",
        ]
    )
    system, _user = _draft_messages("sales", context, {})
    assert system.startswith("Sos Adri, vendedora de Ferretería Norte por WhatsApp.")
    assert "IDENTIDAD" in system
    assert "Ferretería de barrio, atención directa" in system
    assert "CÓMO ACTÚAS" in system
    assert "clara" in system
    assert "CÓMO HABLAS" in system
    assert "directa" in system
    assert "listo" in system
    assert "barato" in system
    assert "EJEMPLOS DE TONO" in system
    assert "Te lo dejo separado" in system
    assert "50 bolivianos" in system
    assert "no copies datos" in system.lower()
    assert "Cuando uses una FAQ o política, dilo con tus palabras" in system
    assert "No recitees visión ni misión." in system
    assert vision not in system
    assert "visión larga" not in system.lower()
    assert system.index("IDENTIDAD") < system.index("Español de Bolivia")
    assert system.index("Español de Bolivia") < system.index("Usá SOLO los datos en FACTS")
    assert 'No digas "confirmo"' in system
    assert "mention_code=true" in system
    assert len(system.split("IDENTIDAD", 1)[1].split("Usá SOLO", 1)[0].split()) <= 140


def test_propose_who_messages_include_estado_from_working_state() -> None:
    state = WorkingState(cart=[{"sku": "h001"}], provider_ref="qr-abc")
    _system, user = _propose_who_messages("recent:", "hola", state)
    assert "ESTADO: carrito=sí, qr_emitido=sí, pago_confirmado=no" in user

    paid = WorkingState(folder=HandoffFolder(payment_state="confirmed"))
    _paid_system, paid_user = _propose_who_messages("recent:", "dirección", paid)
    assert "pago_confirmado=sí" in paid_user
    assert "carrito=no" in paid_user
    assert "qr_emitido=no" in paid_user

    from_context = WorkingState()
    _ctx_system, ctx_user = _propose_who_messages(
        "folder=to=ops payment=confirmed pending=none\nrecent:",
        "hora",
        from_context,
    )
    assert "pago_confirmado=sí" in ctx_user

    pending = WorkingState(
        payment_id=uuid4(),
        folder=HandoffFolder(payment_state="pending"),
    )
    _pending_system, pending_user = _propose_who_messages(
        "folder=to=cobros payment=confirmed pending=none\nrecent:",
        "pagué",
        pending,
    )
    assert "qr_emitido=sí" in pending_user
    assert "pago_confirmado=no" in pending_user


def test_propose_who_system_prioritizes_postventa_before_ops() -> None:
    system, _user = _propose_who_messages("recent:", "hola", WorkingState())
    assert "prioridad" in system.lower()
    assert "No inventes que el pago está confirmado" in system
    assert "live/prenda" in system
    priority_at = system.lower().find("prioridad")
    postventa_at = system.lower().find("postventa", priority_at)
    ops_at = system.lower().find("ops", priority_at)
    assert postventa_at != -1 and ops_at != -1
    assert postventa_at < ops_at
