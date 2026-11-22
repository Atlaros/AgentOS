from factory_os.agents.sales import next_best_action
from factory_os.contracts.employees import identity_for
from factory_os.domain.knowledge import (
    brand_fiche,
    compact_shop_card,
    is_shop_question,
    load_shop_pack,
    match_faq,
    sanitize_shop_pack,
    shop_reply,
)
from factory_os.domain.models import EmployeeRole, NextAction, PILOT_TENANT_ID, WorkingState
from factory_os.domain.seed import normalize
from factory_os.harness.context import compile_context
from tests.conftest import make_shop


def test_shop_pack_omits_empty_socials_and_location() -> None:
    pack = load_shop_pack()
    assert pack["profile"]["name"] == "Authentic Closet"
    assert pack["profile"]["payment"] == "QR"
    assert pack["policies"]["returns"] is False
    card = compact_shop_card(PILOT_TENANT_ID)
    assert "Authentic Closet" in card
    assert "9:00" in card
    assert "QR" in card
    assert "https://www.tiktok.com/@authentic.closet1" in card
    assert "_r=" not in card
    assert "[Completar]" not in card
    assert "instagram.com" not in card.lower()
    assert "facebook.com" not in card.lower()


def test_delivery_faq_is_shop_question_not_catalog() -> None:
    assert is_shop_question("hacen delivery?")
    assert is_shop_question("aceptan devoluciones?")
    assert not is_shop_question("cuánto cuesta la blusa pago1")
    faq = match_faq("hacen envios a santa cruz?")
    assert faq and faq["id"] == "delivery"
    assert "Bolivia" in shop_reply("hacen delivery?")
    tiktok = shop_reply("cuál es su cuenta de tiktok?")
    assert tiktok and "authentic.closet1" in tiktok
    assert "_r=" not in tiktok


def test_blouse_browse_is_not_tiktok_live_faq() -> None:
    """WA incident: stopwords que+una matched tiktok-buy instead of discovering blusas."""
    text = "buehnas tardes estoy bsucando una blusa, que mdelos tiene?"
    assert match_faq(text) is None
    assert not is_shop_question(text)
    assert shop_reply(text) is None
    live = shop_reply("vi una prenda en el live de tiktok, cómo compro?")
    assert live and "código del live" in live.lower()


def test_named_live_product_code_is_catalog_not_faq() -> None:
    """WA incident: 'código del live es pago1' must not ask for the code again."""
    text = "ya recorde el coddigo del live es prueba1 o pago1"
    assert not is_shop_question(text)
    action, skill = next_best_action(WorkingState(), text)
    assert action is NextAction.SEARCH_CATALOG
    assert skill == "product_recommendation"


def test_nba_answers_shop_questions() -> None:
    action, skill = next_best_action(WorkingState(), "hacen delivery?")
    assert action is NextAction.ANSWER
    assert skill == "customer_assistance"


def test_adri_answers_delivery_from_shop_file() -> None:
    shop = make_shop()
    result = shop.handle_turn(shop.store.tenant_id, "59170001901", "hacen delivery?")
    lowered = result.reply.lower()
    assert "delivery" in lowered or "bolivia" in lowered
    assert "ac-test-pay" not in lowered
    draft = next(event for event in reversed(shop.trace.events) if event.operation == "draft")
    hits = draft.payload["facts"]["knowledge_hits"]
    assert any(
        item["id"] in {"delivery", "delivery_zones"} or "delivery" in item["text"].lower()
        for item in hits
    )
    assert "confirmed" not in str(hits).lower()
    returns = shop.handle_turn(shop.store.tenant_id, "59170001901", "aceptan devoluciones?")
    assert "no aceptamos" in returns.reply.lower() or "devolucion" in normalize(returns.reply)


def test_owner_faq_enters_context_and_cannot_set_price_or_payment() -> None:
    from uuid import uuid4

    from factory_os.domain.models import Conversation

    shop = make_shop()
    before = next(
        item
        for item in shop.store.iter_variants()
        if item.variant_sku == "h001-M-VP"
    )
    payments = len(shop.store.list_payments(shop.store.tenant_id))
    edited = shop.store.put_shop_knowledge(
        shop.store.tenant_id,
        {
            "profile": {"name": "Ferretería Norte", "hours": "8:00 a 18:00"},
            "vocabulary": {"item": "artículo"},
            "faqs": [
                {
                    "id": "horario",
                    "category": "Horario",
                    "question": "a qué hora abren",
                    "answer": "Abrimos a las 8.",
                }
            ],
            "price": "1",
            "stock": 99,
            "payment_status": "confirmed",
        },
    )
    assert "price" not in edited
    assert "payment_status" not in edited
    assert shop.store.list_payments(shop.store.tenant_id).__len__() == payments
    assert next(
        item for item in shop.store.iter_variants() if item.variant_sku == "h001-M-VP"
    ).price == before.price
    identity = identity_for(EmployeeRole.SALES, PILOT_TENANT_ID)
    conv = Conversation(id=uuid4(), tenant_id=PILOT_TENANT_ID, customer_id=uuid4())
    text = compile_context(identity, conv, store=shop.store)
    assert "shop=Ferretería Norte" in text
    assert "faqs=horario" in text or "faqs=" in text and "horario" in text
    assert "¿Hacen delivery?" not in text
    result = shop.handle_turn(shop.store.tenant_id, "59170001911", "a qué hora abren")
    assert "8" in result.reply
    assert "artículo" in result.reply or "8" in result.reply


def test_fallback_noun_and_shop_come_from_the_card() -> None:
    """A non-Closet card replaces the customer fallback noun and shop name.

    Price and payments stay on the catalog and the payment list.
    """
    shop = make_shop()
    price = next(item.price for item in shop.store.iter_variants() if item.variant_sku == "h001-M-VP")
    payments = shop.store.list_payments(shop.store.tenant_id)
    shop.store.put_shop_knowledge(
        shop.store.tenant_id,
        {
            "profile": {"name": "Ferretería Norte"},
            "vocabulary": {"item": "artículo"},
        },
    )
    result = shop.handle_turn(shop.store.tenant_id, "59170001921", "hola")
    assert "artículo" in result.reply
    assert "Ferretería Norte" in result.reply
    assert next(item.price for item in shop.store.iter_variants() if item.variant_sku == "h001-M-VP") == price
    assert shop.store.list_payments(shop.store.tenant_id) == payments


def test_sanitize_normalizes_identity_lists_and_tone() -> None:
    pack = sanitize_shop_pack(
        {
            "profile": {
                "vision": "Una visión.\n",
                "mission": ["  ", "Atender hoy"],
                "objectives": "Uno\n\nDos",
                "branches": [
                    {
                        "name": "Centro",
                        "hours": "8 a 18",
                        "address": "Calle Larga 123",
                        "phone": "700",
                        "price": "9",
                    }
                ],
            },
            "policies": {"cancel": "Antes del envío.", "price": "4"},
            "voice": {"tone": "crítica", "address": "usted", "words_avoid": "barato\ngratis"},
            "price": "1",
            "payment_status": "confirmed",
        }
    )
    assert pack["profile"]["vision"] == ["Una visión."]
    assert pack["profile"]["mission"] == ["Atender hoy"]
    assert pack["profile"]["objectives"] == ["Uno", "Dos"]
    assert pack["profile"]["branches"] == [
        {"name": "Centro", "hours": "8 a 18", "address": "Calle Larga 123", "phone": "700"}
    ]
    assert pack["policies"]["cancel"] == "Antes del envío."
    assert "price" not in pack["policies"]
    assert pack["voice"]["tone"] == "critica"
    assert pack["voice"]["address"] == "usted"
    assert pack["voice"]["words_avoid"] == ["barato", "gratis"]
    assert "price" not in pack
    assert "payment_status" not in pack


def test_retrieve_knowledge_snippets_ranks_delivery_and_identity() -> None:
    from factory_os.domain.knowledge_rag import retrieve_knowledge_snippets

    pack = load_shop_pack()
    delivery = retrieve_knowledge_snippets(pack, "hacen delivery")
    assert 1 <= len(delivery) <= 2
    assert any(
        item["kind"] in {"faq", "profile"}
        and (item["id"] in {"delivery", "delivery_zones"} or "delivery" in item["text"].lower())
        for item in delivery
    )
    assert all(set(item) == {"id", "kind", "text"} for item in delivery)
    assert all(len(item["text"]) <= 280 for item in delivery)

    identity = retrieve_knowledge_snippets(pack, "cuál es su visión y quiénes son")
    assert any(item["kind"] == "profile" and item["id"] in {"summary", "differentiator"} for item in identity)
    joined = " ".join(item["text"] for item in identity).lower()
    assert "tendencia" in joined or "tiempo real" in joined


def test_retrieve_keeps_catalog_deferral_and_drops_invented_price() -> None:
    from factory_os.domain.knowledge_rag import retrieve_knowledge_snippets

    pack = {
        "faqs": [
            {
                "id": "precio",
                "question": "cuánto cuesta la blusa",
                "answer": "El precio está en el catálogo, consultá el catálogo.",
                "price": "99",
                "payment_status": "confirmed",
            },
            {
                "id": "caro",
                "question": "precio de la blusa",
                "answer": "La blusa cuesta 99 BOB. Pago confirmado.",
            },
        ]
    }
    hits = retrieve_knowledge_snippets(pack, "cuánto cuesta la blusa")
    assert hits
    assert all(item["id"] != "caro" for item in hits)
    blob = " ".join(item["text"].lower() for item in hits)
    assert "99" not in blob
    assert "confirmed" not in blob
    assert "catalogo" in normalize(blob)


def test_shop_answer_passes_knowledge_hits_without_changing_price() -> None:
    from factory_os.domain.response_goals import phrase_for_response_goal

    shop = make_shop()
    before = next(item.price for item in shop.store.iter_variants() if item.variant_sku == "h001-M-VP")
    payments = list(shop.store.list_payments(shop.store.tenant_id))
    shop.store.put_shop_knowledge(
        shop.store.tenant_id,
        {
            "faqs": [
                {
                    "id": "precio-ficha",
                    "question": "cuánto sale el arreglo",
                    "answer": "El precio está en el catálogo, consultá el catálogo.",
                    "price": "1",
                }
            ],
            "price": "1",
            "payment_status": "confirmed",
        },
    )
    result = shop.handle_turn(shop.store.tenant_id, "59170001931", "cuánto sale el arreglo")
    assert "catalogo" in normalize(result.reply)
    draft = next(event for event in reversed(shop.trace.events) if event.operation == "draft")
    facts = draft.payload["facts"]
    hits = facts["knowledge_hits"]
    assert any(item["id"] == "precio-ficha" for item in hits)
    assert "99" not in str(hits)
    assert "confirmed" not in str(hits).lower()
    assert facts["response_goal"] == phrase_for_response_goal("shop_faq")
    assert next(item.price for item in shop.store.iter_variants() if item.variant_sku == "h001-M-VP") == before
    assert shop.store.list_payments(shop.store.tenant_id) == payments


def test_compact_shop_card_skips_long_vision_and_faq_answers() -> None:
    vision = "Una visión larga de la tienda. " * 12
    pack = {
        "profile": {
            "name": "Ferretería Norte",
            "hours": "8 a 18",
            "vision": vision,
            "mission": ["Misión que no debe salir en la ficha corta del turno."],
            "objectives": ["Objetivo que no entra en la ficha."],
            "branches": [{"name": "Centro", "address": "Calle Larga 123 que no entra"}],
        },
        "faqs": [
            {
                "id": "horario",
                "question": "¿A qué hora abren?",
                "answer": "Abrimos a las ocho en punto y cerramos tarde.",
            }
        ],
        "voice": {"address": "tú", "emojis": "none", "tone": "directa"},
    }
    card = compact_shop_card(PILOT_TENANT_ID, pack)
    assert vision not in card
    assert "Misión que no debe" not in card
    assert "Objetivo que no entra" not in card
    assert "Calle Larga" not in card
    assert "Abrimos a las ocho" not in card
    assert "¿A qué hora abren?" not in card
    assert "faqs=horario" in card
    assert "tone=directa" in card


def test_brand_fiche_is_short_and_skips_vision() -> None:
    vision = "Una visión larga de la tienda. " * 20
    pack = {
        "profile": {
            "name": "Ferretería Norte",
            "summary": "Ferretería de barrio con atención directa.",
            "vision": [vision],
            "mission": ["Misión que no debe recitarse en el prompt."],
            "differentiator": "Este diferenciador no pisa el resumen.",
        },
        "voice": {
            "address": "tú",
            "tone": "directa",
            "traits": ["clara", "breve", "concreta", "extra que no entra"],
            "emojis": "none",
            "words_use": ["listo", "dale"],
            "words_avoid": ["barato"],
            "example_replies": [
                "Te lo separo.",
                "Cuesta 50 Bs hoy",
                "Tercer ejemplo de tono.",
                "Cuarto ejemplo de tono.",
                "Quinto que no entra.",
            ],
        },
    }
    fiche = brand_fiche(pack)
    assert "IDENTIDAD:" in fiche
    assert "Ferretería de barrio con atención directa." in fiche
    assert "Este diferenciador" not in fiche
    assert "Misión que no debe" not in fiche
    assert vision not in fiche
    assert "CÓMO ACTÚAS" in fiche
    assert "extra que no entra" not in fiche
    assert "CÓMO HABLAS" in fiche
    assert "listo" in fiche
    assert "barato" in fiche
    assert "EJEMPLOS DE TONO" in fiche
    assert "Cuesta 50 Bs hoy" in fiche
    assert "Cuarto ejemplo de tono." in fiche
    assert "Quinto que no entra." not in fiche
    assert "no copies datos" in fiche.lower()
    assert len(fiche.split()) <= 120
    assert brand_fiche(None) == ""
    assert brand_fiche({}) == ""
    assert brand_fiche({"profile": {"name": "Authentic Closet"}, "vocabulary": {"item": "prenda"}}) == ""


def test_compact_shop_card_emits_brand_crumbs() -> None:
    vision = "Una visión larga de la tienda. " * 12
    pack = {
        "profile": {
            "name": "Ferretería Norte",
            "summary": "Ferretería de barrio con atención directa y stock del catálogo.",
            "vision": vision,
            "mission": ["Misión que no sale en la tarjeta."],
        },
        "voice": {
            "address": "tú",
            "tone": "directa",
            "emojis": "none",
            "traits": ["clara", "breve", "concreta", "cuarta"],
            "words_use": ["listo", "dale"],
            "words_avoid": ["barato", "gratis"],
            "example_replies": ["Te lo separo si está.", "Sale a 50 Bs", "Tercero que no entra"],
        },
    }
    card = compact_shop_card(PILOT_TENANT_ID, pack)
    assert "identity=Ferretería de barrio" in card
    assert vision not in card
    assert "Misión que no sale" not in card
    assert "\ntone=directa" in card or card.startswith("tone=directa")
    assert "words_use=listo, dale" in card
    assert "words_avoid=barato, gratis" in card
    assert "traits=clara, breve, concreta" in card
    assert "cuarta" not in card
    assert "examples=Te lo separo si está.|Sale a 50 Bs" in card
    assert "Tercero que no entra" not in card
    assert "\n" not in card.split("examples=", 1)[1].split("\n", 1)[0]


def test_closet_seed_without_traits_gets_conduct_not_a_slogan() -> None:
    import copy

    pack = copy.deepcopy(load_shop_pack())
    pack["voice"]["traits"] = []
    fiche = brand_fiche(pack)
    assert "CÓMO ACTÚAS" in fiche
    assert "misión" not in fiche.lower()
    assert "visión" not in fiche.lower()
    other = brand_fiche(
        {"profile": {"name": "Taller Luna", "summary": "Arreglos el día."}, "voice": {}}
    )
    assert "IDENTIDAD" in other
    assert "CÓMO ACTÚAS" not in other


def test_closet_seed_brand_fiche_uses_summary_and_traits() -> None:
    fiche = brand_fiche(load_shop_pack())
    assert "IDENTIDAD:" in fiche
    assert "ropa femenina" in fiche
    assert "CÓMO ACTÚAS" in fiche
    assert "amable" in fiche
    assert "visión" not in fiche.lower()
    assert "misión" not in fiche.lower()
    assert len(fiche.split()) <= 120


def test_context_includes_shop_card_not_full_faq() -> None:
    from uuid import uuid4

    from factory_os.domain.models import Conversation

    identity = identity_for(EmployeeRole.SALES, PILOT_TENANT_ID)
    conv = Conversation(id=uuid4(), tenant_id=PILOT_TENANT_ID, customer_id=uuid4())
    text = compile_context(identity, conv)
    assert "shop=Authentic Closet" in text
    assert "returns=no" in text
    assert "¿Hacen delivery?" not in text
