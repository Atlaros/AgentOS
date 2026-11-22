"""Owner dashboard API — orders, catalog, token gate."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from factory_os.api.main import Settings, create_app
from factory_os.contracts.employees import EmployeeRole, identity_for
from factory_os.domain.models import OrderItem, PaymentStatus, PILOT_TENANT_ID
from factory_os.domain.reports import run_reminders
from factory_os.harness.tools import PermissionDenied
from tests.conftest import api_settings, make_shop, owner_client


def test_orders_and_catalog_endpoints() -> None:
    shop = make_shop()
    customer = shop.store.get_or_create_customer(PILOT_TENANT_ID, "59194000001")
    order = shop.store.create_order(
        PILOT_TENANT_ID,
        customer.id,
        OrderItem("h001-M-VP", "blusa de hilo jubenil", 1, Decimal("145.00"), "BOB"),
    )
    assert order.public_number and order.public_number.startswith("AC-")
    client = owner_client(shop)
    orders = client.get("/api/orders")
    assert orders.status_code == 200
    body = orders.json()["orders"]
    assert len(body) >= 1
    row = next(o for o in body if o["id"] == str(order.id))
    assert row["public_number"] == order.public_number
    assert row["delivered_at"] is None
    marked = client.post(f"/api/orders/{order.id}/delivered")
    assert marked.status_code == 200
    assert marked.json()["status"] == "delivered"
    assert marked.json()["delivered_at"]
    catalog = client.get("/api/catalog?limit=200")
    assert catalog.status_code == 200
    products = catalog.json()["products"]
    assert len(products) >= 1
    unpaid = next(p for p in products if p["variant_sku"] == "h001-M-VP")
    assert unpaid["sold"] is False
    cancelled = client.post(f"/api/orders/{order.id}/status", json={"status": "cancelled"})
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    after = client.get("/api/catalog?limit=200").json()["products"]
    cleared = next(p for p in after if p["variant_sku"] == "h001-M-VP")
    assert cleared["sold"] is False
    added = client.post(
        "/api/catalog",
        json={
            "codigo": "n900",
            "name": "Pollera nueva",
            "price": "80",
            "stock": 2,
            "category": "faldas",
            "subcategory": "midi",
            "material": "jean",
            "talla": "M",
            "color": "negro",
            "description": "pollera de prueba",
        },
    )
    assert added.status_code == 200
    assert added.json()["codigo"] == "n900"
    assert added.json()["variant_sku"] == "n900-M-N"
    stored = next(p for p in client.get("/api/catalog?limit=200").json()["products"] if p["codigo"] == "n900")
    assert stored["material"] == "jean"
    assert stored["talla"] == "M"
    assert stored["color"] == "negro"
    assert stored["description"] == "pollera de prueba"
    assert stored["available"] is True
    marked = client.post(
        f"/api/catalog/{stored['variant_sku']}/availability",
        json={"available": False},
    )
    assert marked.status_code == 200
    assert marked.json()["available"] is False
    assert marked.json()["stock"] == 0
    listed = client.get("/api/catalog?limit=200").json()["products"]
    sold_row = next(p for p in listed if p["variant_sku"] == stored["variant_sku"])
    assert sold_row["available"] is False
    assert sold_row["stock"] == 0
    restored = client.post(
        f"/api/catalog/{stored['variant_sku']}/availability",
        json={"available": True},
    )
    assert restored.status_code == 200
    assert restored.json()["available"] is True
    assert restored.json()["stock"] >= 1
    bad = client.post(f"/api/orders/{order.id}/status", json={"status": "paid"})
    assert bad.status_code == 400
    missing = client.post("/api/catalog/no-existe-sku/availability", json={"available": False})
    assert missing.status_code == 404


def test_owner_customer_file_shows_orders_chats_and_notes() -> None:
    shop = make_shop()
    customer = shop.store.get_or_create_customer(PILOT_TENANT_ID, "59170002001")
    shop.store.update_customer(PILOT_TENANT_ID, customer.wa_number, "Ana", "Equipetrol")
    shop.store.get_or_create_conversation(PILOT_TENANT_ID, customer)
    shop.handle_turn(PILOT_TENANT_ID, customer.wa_number, "hola, busco una blusa")
    order = shop.store.create_order(
        PILOT_TENANT_ID,
        customer.id,
        OrderItem("h001-M-VP", "blusa de hilo", 1, Decimal("145.00"), "BOB"),
    )
    client = owner_client(shop)
    listed = client.get("/api/customers")
    assert listed.status_code == 200
    row = next(item for item in listed.json()["customers"] if item["id"] == str(customer.id))
    assert row["name"] == "Ana"
    assert row["order_count"] == 1
    assert row["note_count"] == 0
    assert row["conversation_count"] >= 1
    detail = client.get(f"/api/customers/{customer.id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["address"] == "Equipetrol"
    assert body["name"] == "Ana"
    assert body["preferences"] == {}
    assert body["orders"][0]["id"] == str(order.id)
    assert body["orders"][0]["payment_status"] is None
    assert body["orders"][0]["delivery"] is None
    chat = body["conversations"][0]
    assert chat["message_count"] >= 1
    assert "human_takeover" in chat
    assert "needs_human" in chat
    assert "cart" in chat
    empty = client.post(f"/api/customers/{customer.id}/notes", json={"body": "   "})
    assert empty.status_code == 400
    noted = client.post(
        f"/api/customers/{customer.id}/notes",
        json={"body": "Prefiere envío por la tarde"},
    )
    assert noted.status_code == 200
    again = client.get(f"/api/customers/{customer.id}").json()
    assert again["notes"][-1]["body"] == "Prefiere envío por la tarde"
    missing = client.get("/api/customers/00000000-0000-0000-0000-000000000000")
    assert missing.status_code == 404


def test_customer_file_hydrates_empty_identity_from_latest_delivery() -> None:
    shop = make_shop()
    customer = shop.store.get_or_create_customer(PILOT_TENANT_ID, "59170002002")
    assert not (customer.name or "").strip()
    assert not (customer.address or "").strip()
    older = shop.store.create_order(
        PILOT_TENANT_ID,
        customer.id,
        OrderItem("h002-S-N", "pollera", 1, Decimal("80.00"), "BOB"),
    )
    older.created_at = datetime(2026, 1, 1, tzinfo=UTC)
    shop.store.create_delivery(PILOT_TENANT_ID, older.id, "Calle Vieja 1", "Vieja")
    newer = shop.store.create_order(
        PILOT_TENANT_ID,
        customer.id,
        OrderItem("h001-M-VP", "blusa de hilo", 1, Decimal("145.00"), "BOB"),
        discount_amount=Decimal("5"),
    )
    newer.created_at = datetime(2026, 6, 1, tzinfo=UTC)
    payment = shop.store.create_payment(
        PILOT_TENANT_ID,
        newer.id,
        "fake",
        "qr-lucia",
        Decimal("140.00"),
        "BOB",
        "QR:lucia",
        customer_id=customer.id,
    )
    shop.store.confirm_from_adapter(payment.provider_ref)
    shop.store.create_delivery(PILOT_TENANT_ID, newer.id, "Calle 12", "Lucía")
    client = owner_client(shop)
    detail = client.get(f"/api/customers/{customer.id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["name"] == "Lucía"
    assert body["address"] == "Calle 12"
    assert body["preferences"] == {}
    row = next(item for item in body["orders"] if item["id"] == str(newer.id))
    assert row["payment_status"] == "confirmed"
    assert row["provider_ref"] == "qr-lucia"
    assert row["discount"] == "5"
    assert row["currency"] == "BOB"
    assert row["total"] == "140.00"
    assert row["delivery"] == {"address": "Calle 12", "recipient_name": "Lucía"}
    listed = next(item for item in client.get("/api/customers").json()["customers"] if item["id"] == str(customer.id))
    assert listed["name"] == "Lucía"
    assert listed["address"] == "Calle 12"
    stored = shop.store.get_customer(PILOT_TENANT_ID, customer.id)
    assert stored is not None
    assert stored.name == "Lucía"
    assert stored.address == "Calle 12"


def test_customer_file_without_delivery_does_not_invent_name() -> None:
    shop = make_shop()
    customer = shop.store.get_or_create_customer(PILOT_TENANT_ID, "59170002009")
    shop.store.create_order(
        PILOT_TENANT_ID,
        customer.id,
        OrderItem("h001-M-VP", "blusa", 1, Decimal("145.00"), "BOB"),
    )
    client = owner_client(shop)
    body = client.get(f"/api/customers/{customer.id}").json()
    assert not (body["name"] or "").strip()
    assert not (body["address"] or "").strip()
    listed = next(item for item in client.get("/api/customers").json()["customers"] if item["id"] == str(customer.id))
    assert not (listed["name"] or "").strip()


def test_customer_file_hydration_keeps_fields_already_set() -> None:
    shop = make_shop()
    customer = shop.store.get_or_create_customer(PILOT_TENANT_ID, "59170002003")
    shop.store.update_customer(PILOT_TENANT_ID, customer.wa_number, "Ana", None)
    order = shop.store.create_order(
        PILOT_TENANT_ID,
        customer.id,
        OrderItem("h001-M-VP", "blusa", 1, Decimal("145.00"), "BOB"),
    )
    shop.store.create_delivery(PILOT_TENANT_ID, order.id, "Zona Sur", "Lucía")
    client = owner_client(shop)
    body = client.get(f"/api/customers/{customer.id}").json()
    assert body["name"] == "Ana"
    assert body["address"] == "Zona Sur"


def test_customer_file_shows_saved_preferences() -> None:
    shop = make_shop()
    customer = shop.store.get_or_create_customer(PILOT_TENANT_ID, "59170002004")
    shop.store.put_customer_preferences(
        PILOT_TENANT_ID,
        customer.id,
        {"color": "negro", "size": "M"},
    )
    client = owner_client(shop)
    body = client.get(f"/api/customers/{customer.id}").json()
    assert body["preferences"] == {"color": "negro", "size": "M"}


def test_customer_file_conversation_activity_flags() -> None:
    shop = make_shop()
    customer = shop.store.get_or_create_customer(PILOT_TENANT_ID, "59170002005")
    conv = shop.store.get_or_create_conversation(PILOT_TENANT_ID, customer)
    conv.state.human_takeover = True
    conv.state.needs_human = True
    conv.state.cart = [
        {
            "variant_sku": "h001-M-VP",
            "name": "blusa de hilo",
            "quantity": 1,
            "unit_price": "145.00",
            "currency": "BOB",
        }
    ]
    shop.store.append_message(conv, "customer", "quiero la blusa")
    shop.store.save_conversation_state(conv)
    client = owner_client(shop)
    body = client.get(f"/api/customers/{customer.id}").json()
    row = body["conversations"][0]
    assert row["id"] == str(conv.id)
    assert row["message_count"] == 1
    assert row["last_text"] == "quiero la blusa"
    assert row["human_takeover"] is True
    assert row["needs_human"] is True
    assert row["cart"]["lines"][0]["name"] == "blusa de hilo"
    assert row["cart"]["total"] == "145.00"
    listed = next(item for item in client.get("/api/customers").json()["customers"] if item["id"] == str(customer.id))
    assert listed["conversation_count"] == 1


def test_owner_knowledge_api_strips_price_and_payment() -> None:
    shop = make_shop()
    client = owner_client(shop)
    saved = client.put(
        "/api/knowledge",
        json={
            "profile": {"name": "Ferretería Norte"},
            "vocabulary": {"item": "artículo"},
            "faqs": [
                {
                    "id": "horario",
                    "question": "a qué hora abren",
                    "answer": "Abrimos a las 8.",
                }
            ],
            "price": "9",
            "payment_status": "confirmed",
        },
    )
    assert saved.status_code == 200
    body = saved.json()
    assert body["profile"]["name"] == "Ferretería Norte"
    assert "price" not in body
    assert "payment_status" not in body
    listed = client.get("/api/knowledge")
    assert listed.status_code == 200
    assert any(row["id"] == "horario" for row in listed.json()["faqs"])


def test_owner_knowledge_round_trips_identity_voice_and_rejects_price() -> None:
    shop = make_shop()
    client = owner_client(shop)
    vision = "Acompañar cada obra del barrio con herramienta a mano."
    saved = client.put(
        "/api/knowledge",
        json={
            "profile": {
                "name": "Ferretería Norte",
                "vision": vision,
                "mission": ["Resolver el faltante del día", ""],
                "objectives": "Stock visible\nEntrega en el día",
                "branches": [
                    {
                        "name": "Centro",
                        "hours": "8 a 18",
                        "address": "Calle Larga 123",
                        "phone": "7001001",
                        "price": "10",
                    }
                ],
            },
            "policies": {"cancel": "Antes del despacho.", "claims": "Al encargado.", "price": "4"},
            "faqs": [
                {"id": "horario", "question": "a qué hora abren", "answer": "A las 8."},
                {"id": "envio", "question": "hacen envíos", "answer": "Sí, en la ciudad."},
            ],
            "voice": {
                "address": "tú",
                "tone": "directa",
                "words_use": ["listo", "te lo separo"],
                "words_avoid": ["barato"],
                "example_replies": ["Te lo separo si está en stock."],
            },
            "price": "9",
            "payment_status": "confirmed",
            "stock": 3,
        },
    )
    assert saved.status_code == 200
    body = saved.json()
    assert "price" not in body
    assert "payment_status" not in body
    assert "stock" not in body
    assert "price" not in body["profile"]["branches"][0]
    assert "price" not in body["policies"]
    listed = client.get("/api/knowledge")
    assert listed.status_code == 200
    got = listed.json()
    assert got["profile"]["name"] == "Ferretería Norte"
    assert got["profile"]["vision"] == [vision]
    assert got["profile"]["mission"] == ["Resolver el faltante del día"]
    assert got["profile"]["objectives"] == ["Stock visible", "Entrega en el día"]
    assert got["profile"]["branches"] == [
        {"name": "Centro", "hours": "8 a 18", "address": "Calle Larga 123", "phone": "7001001"}
    ]
    assert got["policies"]["cancel"] == "Antes del despacho."
    assert got["policies"]["claims"] == "Al encargado."
    ids = {row["id"] for row in got["faqs"]}
    assert {"horario", "envio", "delivery"} <= ids
    assert got["voice"]["tone"] == "directa"
    assert got["voice"]["words_use"] == ["listo", "te lo separo"]
    assert got["voice"]["words_avoid"] == ["barato"]
    assert got["voice"]["example_replies"] == ["Te lo separo si está en stock."]
    assert "price" not in got
    assert "payment_status" not in got


def _faq_ids(body: dict) -> set[str]:
    return {row["id"] for row in body["faqs"]}


def test_owner_knowledge_put_one_faq_keeps_closet_list() -> None:
    shop = make_shop()
    client = owner_client(shop)
    before = client.get("/api/knowledge")
    assert before.status_code == 200
    before_ids = _faq_ids(before.json())
    assert len(before_ids) >= 8
    assert "delivery" in before_ids
    saved = client.put(
        "/api/knowledge",
        json={
            "faqs": [
                {
                    "id": "domingos",
                    "category": "Horario",
                    "question": "¿Abren los domingos?",
                    "answer": "No abrimos los domingos.",
                }
            ]
        },
    )
    assert saved.status_code == 200
    assert "domingos" in _faq_ids(saved.json())
    assert before_ids <= _faq_ids(saved.json())
    listed = client.get("/api/knowledge")
    assert listed.status_code == 200
    assert before_ids <= _faq_ids(listed.json())
    assert "domingos" in _faq_ids(listed.json())


def test_owner_knowledge_faq_replace_marker_drops_removed_id() -> None:
    shop = make_shop()
    client = owner_client(shop)
    current = client.get("/api/knowledge").json()["faqs"]
    assert any(row["id"] == "where" for row in current)
    without_where = [row for row in current if row["id"] != "where"]
    saved = client.put(
        "/api/knowledge",
        json={
            "faqs": [
                {"id": "__faq_list_replaces__", "question": "", "answer": ""},
                *without_where,
            ]
        },
    )
    assert saved.status_code == 200
    assert "where" not in _faq_ids(saved.json())
    assert "__faq_list_replaces__" not in _faq_ids(saved.json())
    assert "delivery" in _faq_ids(saved.json())
    listed = client.get("/api/knowledge")
    assert "where" not in _faq_ids(listed.json())
    stored = listed.json()["faqs"]
    without_delivery = [row for row in stored if row["id"] != "delivery"]
    again = client.put(
        "/api/knowledge",
        json={
            "faqs": [
                {"id": "__faq_list_replaces__", "question": "", "answer": ""},
                *without_delivery,
            ]
        },
    )
    assert again.status_code == 200
    final = client.get("/api/knowledge")
    final_ids = _faq_ids(final.json())
    assert "delivery" not in final_ids
    assert "where" not in final_ids
    assert "sizes" in final_ids


def test_owner_knowledge_profile_put_leaves_faqs_unchanged() -> None:
    shop = make_shop()
    client = owner_client(shop)
    before = client.get("/api/knowledge")
    assert before.status_code == 200
    before_body = before.json()
    before_ids = [row["id"] for row in before_body["faqs"]]
    assert len(before_ids) >= 8
    saved = client.put(
        "/api/knowledge",
        json={"profile": {"summary": "La lista de preguntas no se toca."}},
    )
    assert saved.status_code == 200
    assert "faqs" in saved.json()
    assert [row["id"] for row in saved.json()["faqs"]] == before_ids
    listed = client.get("/api/knowledge")
    assert listed.status_code == 200
    got = listed.json()
    assert [row["id"] for row in got["faqs"]] == before_ids
    assert got["profile"]["summary"] == "La lista de preguntas no se toca."
    assert got["profile"]["name"] == before_body["profile"]["name"]


def test_owner_knowledge_propose_does_not_write() -> None:
    shop = make_shop()
    client = owner_client(shop)
    before = client.get("/api/knowledge")
    assert before.status_code == 200
    before_ids = [row["id"] for row in before.json()["faqs"]]
    proposed = client.post(
        "/api/knowledge/propose",
        json={
            "text": "P: ¿Abren los feriados?\nR: No abrimos feriados.",
            "kind": "faq",
        },
    )
    assert proposed.status_code == 200
    body = proposed.json()
    assert body["wrote"] is False
    assert body["source"] == {"filename": None, "chars": len("P: ¿Abren los feriados?\nR: No abrimos feriados.")}
    assert body["proposal"]["faqs"][0]["question"] == "¿Abren los feriados?"
    assert "price" not in body["proposal"]
    after = client.get("/api/knowledge")
    assert [row["id"] for row in after.json()["faqs"]] == before_ids
    assert shop.store.get_shop_knowledge(PILOT_TENANT_ID) is None


def test_owner_knowledge_propose_then_put_writes_vision_and_faq() -> None:
    shop = make_shop()
    client = owner_client(shop)
    text = (
        "Visión\nUna tienda que confirma antes de escribir.\n\n"
        "P: ¿Hay feriados?\nR: Cerramos los feriados.\n"
    )
    proposed = client.post("/api/knowledge/propose", json={"text": text, "filename": "ficha.txt"})
    assert proposed.status_code == 200
    assert proposed.json()["wrote"] is False
    assert proposed.json()["source"]["filename"] == "ficha.txt"
    saved = client.put("/api/knowledge", json=proposed.json()["proposal"])
    assert saved.status_code == 200
    listed = client.get("/api/knowledge")
    assert listed.status_code == 200
    got = listed.json()
    assert got["profile"]["vision"] == ["Una tienda que confirma antes de escribir."]
    assert any(row["question"] == "¿Hay feriados?" for row in got["faqs"])
    assert shop.store.get_shop_knowledge(PILOT_TENANT_ID) is not None


def test_owner_knowledge_propose_rejects_pdf_and_empty_text() -> None:
    shop = make_shop()
    client = owner_client(shop)
    rejected = client.post(
        "/api/knowledge/propose",
        json={"text": "hola", "filename": "manual.pdf"},
    )
    assert rejected.status_code == 400
    assert rejected.json()["detail"] == "unsupported_document"
    binary = client.post(
        "/api/knowledge/propose",
        files={"file": ("manual.pdf", b"%PDF-1.4\nbinary", "application/pdf")},
    )
    assert binary.status_code == 400
    assert binary.json()["detail"] == "unsupported_document"
    empty = client.post("/api/knowledge/propose", json={"text": "   "})
    assert empty.status_code == 400
    assert shop.store.get_shop_knowledge(PILOT_TENANT_ID) is None


def test_owner_knowledge_propose_strips_price_key_from_prose() -> None:
    shop = make_shop()
    client = owner_client(shop)
    proposed = client.post(
        "/api/knowledge/propose",
        json={"text": 'Visión\nDice "price": 99 en el texto.\n'},
    )
    assert proposed.status_code == 200
    assert proposed.json()["wrote"] is False
    proposal = proposed.json()["proposal"]
    assert "price" not in proposal
    assert "price" not in proposal["profile"]
    assert shop.store.get_shop_knowledge(PILOT_TENANT_ID) is None


def test_owner_cash_metrics_and_stock_receive() -> None:
    shop = make_shop()
    client = owner_client(shop)
    cash = client.get("/api/cash")
    assert cash.status_code == 200
    assert cash.json()["balance"] == "0"
    assert cash.json()["count"] == 0
    assert cash.json()["session"] is None
    opened = client.post("/api/cash/session/open", json={"opening_float": "0"})
    assert opened.status_code == 200
    posted = client.post(
        "/api/cash",
        json={"direction": "in", "amount": "50", "reason": "venta mostrador"},
    )
    assert posted.status_code == 200
    assert posted.json()["amount"] == "50"
    after = client.get("/api/cash").json()
    assert after["balance"] == "50"
    assert after["count"] == 1
    assert after["movements"][0]["reason"] == "venta mostrador"
    bad = client.post("/api/cash", json={"direction": "sideways", "amount": "1"})
    assert bad.status_code == 400

    metrics = client.get("/api/metrics")
    assert metrics.status_code == 200
    body = metrics.json()
    assert "orders" in body
    assert "payments_confirmed" in body
    assert "low_stock_count" in body

    low = client.get("/api/stock/low")
    assert low.status_code == 200
    assert low.json()["contact_supplier"] is False
    before = next(p for p in client.get("/api/catalog?limit=200").json()["products"] if p["variant_sku"] == "h001-M-VP")
    received = client.post(
        "/api/stock/receive",
        json={"variant_sku": "h001-M-VP", "quantity": 3, "unit_cost": "10"},
    )
    assert received.status_code == 200
    assert received.json()["received"] == 3
    assert received.json()["stock"] == before["stock"] + 3
    assert received.json()["payment_method"] == "cash"
    no_cost = client.post("/api/stock/receive", json={"variant_sku": "h001-M-VP", "quantity": 1})
    assert no_cost.status_code == 400
    missing = client.post(
        "/api/stock/receive",
        json={"variant_sku": "no-existe", "quantity": 1, "unit_cost": "1"},
    )
    assert missing.status_code == 404


def test_owner_token_required_when_configured() -> None:
    shop = make_shop()
    client = TestClient(create_app(shop, Settings(owner_dashboard_token="secret")))
    denied = client.get("/api/conversations")
    assert denied.status_code == 401
    ok = client.get("/api/conversations", headers={"Authorization": "Bearer secret"})
    assert ok.status_code == 200


def test_owner_api_fails_closed_without_token() -> None:
    client = TestClient(create_app(make_shop(), api_settings(owner_dashboard_token="")))
    for path in ("/api/conversations", "/api/orders", "/api/catalog", "/api/cash", "/api/metrics"):
        response = client.get(path, headers={"Authorization": "Bearer "})
        assert response.status_code == 503, path
        assert response.json()["detail"] == "owner_auth_not_configured"


def test_owner_api_rejects_wrong_token() -> None:
    client = TestClient(create_app(make_shop(), api_settings()))
    assert client.get("/api/orders").status_code == 401
    assert client.get("/api/orders", headers={"Authorization": "Bearer otro"}).status_code == 401


def test_owner_reports_alerts_and_reminders_do_not_sell_or_confirm() -> None:
    shop = make_shop()
    now = datetime(2026, 11, 8, tzinfo=UTC)
    quiet = shop.store.get_or_create_customer(PILOT_TENANT_ID, "59170003001")
    quiet_chat = shop.store.get_or_create_conversation(PILOT_TENANT_ID, quiet)
    shop.store.append_message(quiet_chat, "customer", "hola")
    quiet_chat.last_message_at = now - timedelta(days=40)

    recent = shop.store.get_or_create_customer(PILOT_TENANT_ID, "59170003002")
    recent_chat = shop.store.get_or_create_conversation(PILOT_TENANT_ID, recent)
    shop.store.append_message(recent_chat, "customer", "sigo acá")
    recent_chat.last_message_at = now

    buyer = shop.store.get_or_create_customer(PILOT_TENANT_ID, "59170003003")
    buyer_chat = shop.store.get_or_create_conversation(PILOT_TENANT_ID, buyer)
    shop.store.append_message(buyer_chat, "customer", "gracias")
    buyer_chat.last_message_at = now - timedelta(days=40)
    bought = shop.store.create_order(
        PILOT_TENANT_ID,
        buyer.id,
        OrderItem("h001-M-VP", "blusa", 1, Decimal("145.00"), "BOB"),
        status="delivered",
    )
    bought.created_at = now - timedelta(days=40)
    paid = shop.store.create_payment(
        PILOT_TENANT_ID,
        bought.id,
        "fake",
        "pay-confirmed",
        Decimal("145.00"),
        "BOB",
        "QR:confirmed",
        customer_id=buyer.id,
    )
    paid.status = PaymentStatus.CONFIRMED

    debtor = shop.store.get_or_create_customer(PILOT_TENANT_ID, "59170003004")
    debtor_chat = shop.store.get_or_create_conversation(PILOT_TENANT_ID, debtor)
    shop.store.append_message(debtor_chat, "customer", "el qr")
    debtor_chat.last_message_at = now
    owed = shop.store.create_order(
        PILOT_TENANT_ID,
        debtor.id,
        OrderItem("h001-M-VP", "blusa", 1, Decimal("145.00"), "BOB"),
    )
    expired = shop.store.create_payment(
        PILOT_TENANT_ID,
        owed.id,
        "fake",
        "pay-expired",
        Decimal("145.00"),
        "BOB",
        "QR:expired",
        customer_id=debtor.id,
    )
    expired.status = PaymentStatus.EXPIRED

    client = owner_client(shop)
    alerts = client.get("/api/alerts")
    assert alerts.status_code == 200
    overdue_refs = {row["provider_ref"] for row in alerts.json()["overdue_payments"]}
    assert overdue_refs == {"pay-expired"}
    inactive_ids = {row["id"] for row in alerts.json()["inactive_customers"]}
    assert str(quiet.id) in inactive_ids
    assert str(buyer.id) in inactive_ids
    assert str(recent.id) not in inactive_ids
    assert str(debtor.id) not in inactive_ids

    orders_csv = client.get("/api/reports/orders.csv")
    payments_csv = client.get("/api/reports/payments.csv")
    stock_csv = client.get("/api/reports/stock.csv")
    assert orders_csv.status_code == 200
    assert payments_csv.status_code == 200
    assert stock_csv.status_code == 200
    assert bought.public_number in orders_csv.text
    assert "pay-expired" in payments_csv.text
    assert "145.00" in payments_csv.text
    assert "h001-M-VP" in stock_csv.text
    assert shop.store.get_payment(PILOT_TENANT_ID, expired.id).status is PaymentStatus.EXPIRED

    analyst = identity_for(EmployeeRole.ANALYST, PILOT_TENANT_ID)
    held = run_reminders(shop.store, analyst, shop.channel, shop.tools, now=now, send=True)
    assert held["sent"] == []
    assert shop.channel.sent == []
    assert shop.store.get_payment(PILOT_TENANT_ID, expired.id).status is PaymentStatus.EXPIRED

    cobros = identity_for(EmployeeRole.COBROS, PILOT_TENANT_ID)
    collected = run_reminders(shop.store, cobros, shop.channel, shop.tools, now=now, send=True)
    assert [item["kind"] for item in collected["sent"]] == ["collections"]
    assert shop.channel.sent == [(debtor.wa_number, collected["sent"][0]["body"])]
    assert "145" not in shop.channel.sent[0][1]
    assert "te recomiendo" not in shop.channel.sent[0][1].lower()
    assert shop.store.get_payment(PILOT_TENANT_ID, expired.id).status is PaymentStatus.EXPIRED

    postventa = identity_for(EmployeeRole.POSTVENTA, PILOT_TENANT_ID)
    followed = run_reminders(shop.store, postventa, shop.channel, shop.tools, now=now, send=True)
    kinds = sorted(item["kind"] for item in followed["sent"])
    assert kinds == ["follow_up", "repurchase"]
    assert all("145" not in item["body"] for item in followed["sent"])
    assert shop.store.get_payment(PILOT_TENANT_ID, expired.id).status is PaymentStatus.EXPIRED

    again = run_reminders(shop.store, cobros, shop.channel, shop.tools, now=now, send=True)
    assert again["sent"] == []
    assert len(shop.channel.sent) == 3

    parked = client.post("/api/reminders/run", json={"send": False})
    assert parked.status_code == 200
    assert parked.json()["sent"] == []


def test_panel_staff_write_is_attributed_and_cannot_administer() -> None:
    shop = make_shop()
    client = owner_client(shop)
    created = client.post(
        "/api/panel/users",
        json={
            "name": "Ana Operaciones",
            "email": "ana@taller.local",
            "role": "staff",
            "secret": "staff-secret",
        },
    )
    assert created.status_code == 200
    user = created.json()
    assert user["role"] == "staff"
    assert user["name"] == "Ana Operaciones"
    assert "secret" not in user
    assert "secret_hash" not in user

    staff = TestClient(create_app(shop, api_settings()))
    staff.headers["Authorization"] = "Bearer staff-secret"
    forbidden_user = staff.post(
        "/api/panel/users",
        json={
            "name": "Otra",
            "email": "otra@taller.local",
            "role": "staff",
            "secret": "otra-clave-1",
        },
    )
    assert forbidden_user.status_code == 403
    forbidden_knowledge = staff.put("/api/knowledge", json={"name": "Otra marca"})
    assert forbidden_knowledge.status_code == 403
    assert staff.get("/api/panel/audit").status_code == 403

    customer = shop.store.get_or_create_customer(PILOT_TENANT_ID, "59170004001")
    note = staff.post(
        f"/api/customers/{customer.id}/notes",
        json={"body": "Llamar a la tarde"},
    )
    assert note.status_code == 200

    audit = client.get("/api/panel/audit")
    assert audit.status_code == 200
    events = audit.json()["events"]
    note_events = [row for row in events if row["path"].endswith("/notes")]
    assert note_events[-1]["actor_name"] == "Ana Operaciones"
    assert note_events[-1]["actor_role"] == "staff"
    assert all(row["actor_role"] in {"owner", "staff"} for row in events)
    assert all(row["actor_name"] != "Adri" for row in events)

    login = TestClient(create_app(shop, api_settings())).post(
        "/api/panel/login",
        json={"email": "ana@taller.local", "secret": "staff-secret"},
    )
    assert login.status_code == 200
    assert login.json()["actor_id"] == user["id"]
    assert login.json()["role"] == "staff"
    assert "secret" not in login.json()
    impostor = TestClient(create_app(shop, api_settings()))
    assert impostor.get("/api/orders", headers={"Authorization": "Bearer Adri"}).status_code == 401


def test_issued_invoice_does_not_confirm_payment_and_ledger_follows_facts() -> None:
    shop = make_shop()
    client = owner_client(shop)
    customer = shop.store.get_or_create_customer(PILOT_TENANT_ID, "59170005001")
    order = shop.store.create_order(
        PILOT_TENANT_ID,
        customer.id,
        OrderItem("h001-M-VP", "blusa", 1, Decimal("145.00"), "BOB"),
    )
    pending = shop.store.create_payment(
        PILOT_TENANT_ID,
        order.id,
        "fake",
        "pay-open",
        Decimal("145.00"),
        "BOB",
        "QR:open",
        customer_id=customer.id,
    )
    sales = identity_for(EmployeeRole.SALES, PILOT_TENANT_ID)
    with pytest.raises(PermissionDenied):
        shop.tools.execute(sales, "invoice.issue", {"order_id": str(order.id)}, channel="internal")

    issued = client.post("/api/invoices", json={"order_id": str(order.id)})
    assert issued.status_code == 200
    assert issued.json()["status"] == "issued"
    assert "pay-open" not in issued.text
    assert shop.store.get_payment(PILOT_TENANT_ID, pending.id).status is PaymentStatus.PENDING
    before = client.get("/api/ledger")
    assert before.status_code == 200
    assert all(row["source"] != "payment" for row in before.json()["entries"])

    shop.store.confirm_from_adapter("pay-open")
    assert shop.store.get_payment(PILOT_TENANT_ID, pending.id).status is PaymentStatus.CONFIRMED
    posted = client.get("/api/ledger").json()["entries"]
    income = [row for row in posted if row["source"] == "payment"]
    assert len(income) == 1
    assert income[0]["direction"] == "in"
    assert income[0]["amount"] == "145.00"
    shop.store.confirm_from_adapter("pay-open")
    assert len([row for row in client.get("/api/ledger").json()["entries"] if row["source"] == "payment"]) == 1

    assert client.post("/api/cash/session/open", json={"opening_float": "0"}).status_code == 200
    cash = client.post("/api/cash", json={"direction": "out", "amount": "10", "reason": "bolsas"})
    assert cash.status_code == 200
    assert any(
        row["source"] == "cash" and row["direction"] == "out" and row["amount"] == "10"
        for row in client.get("/api/ledger").json()["entries"]
    )

    received = client.post(
        "/api/stock/receive",
        json={"variant_sku": "h001-M-VP", "quantity": 2, "unit_cost": "30"},
    )
    assert received.status_code == 200
    purchase = next(
        row for row in client.get("/api/ledger").json()["entries"] if row["source"] == "purchase"
    )
    assert purchase["direction"] == "out"
    assert purchase["amount"] == "60.00"
    again = client.post("/api/invoices", json={"order_id": str(order.id)})
    assert again.status_code == 200
    assert again.json()["status"] == "issued"
    assert shop.store.get_payment(PILOT_TENANT_ID, pending.id).status is PaymentStatus.CONFIRMED


def _paid_order(shop, wa: str, *, name: str | None = None, address: str | None = None, confirm: bool = True):
    customer = shop.store.get_or_create_customer(PILOT_TENANT_ID, wa)
    if name or address:
        shop.store.update_customer(PILOT_TENANT_ID, wa, name, address)
    order = shop.store.create_order(
        PILOT_TENANT_ID,
        customer.id,
        OrderItem("h001-M-VP", "blusa de hilo", 1, Decimal("145.00"), "BOB"),
    )
    payment = shop.store.create_payment(
        PILOT_TENANT_ID,
        order.id,
        "fake",
        f"qr-{wa}",
        Decimal("145.00"),
        "BOB",
        f"QR:{wa}",
        customer_id=customer.id,
    )
    if confirm:
        variant = shop.store.get_variant(PILOT_TENANT_ID, "h001-M-VP")
        if variant is None or variant.stock < 1 or variant.attributes.get("disabled"):
            shop.store.set_variant_availability(
                PILOT_TENANT_ID, "h001-M-VP", available=True, stock=1
            )
        shop.store.confirm_from_adapter(payment.provider_ref)
    return customer, order


def test_manual_delivery_after_confirmed_payment_fills_blank_customer() -> None:
    shop = make_shop()
    customer, order = _paid_order(shop, "59170003001")
    assert not (customer.name or "").strip()
    assert not (customer.address or "").strip()
    kept, kept_order = _paid_order(shop, "59170003002", name="Ana", address="Zona Norte")
    client = owner_client(shop)

    missing = client.post(
        "/api/orders/00000000-0000-0000-0000-000000000099/delivery",
        json={"recipient_name": "Lucía", "address": "Calle 9"},
    )
    assert missing.status_code == 404
    empty = client.post(
        f"/api/orders/{order.id}/delivery",
        json={"recipient_name": "  ", "address": "Calle 9"},
    )
    assert empty.status_code == 400

    posted = client.post(
        f"/api/orders/{order.id}/delivery",
        json={"recipient_name": " Lucía ", "address": " Calle 9 "},
    )
    assert posted.status_code == 200
    body = posted.json()
    assert body["order_id"] == str(order.id)
    assert body["delivery"] == {"address": "Calle 9", "recipient_name": "Lucía"}
    assert body["customer"]["name"] == "Lucía"
    assert body["customer"]["address"] == "Calle 9"
    assert body["customer"]["wa_number"] == "59170003001"
    stored = shop.store.get_customer(PILOT_TENANT_ID, customer.id)
    assert stored is not None
    assert stored.name == "Lucía"
    assert stored.address == "Calle 9"

    listed = client.get("/api/orders").json()["orders"]
    row = next(item for item in listed if item["id"] == str(order.id))
    assert row["has_delivery"] is True
    assert row["delivery"] == {"address": "Calle 9", "recipient_name": "Lucía"}

    again = client.post(
        f"/api/orders/{order.id}/delivery",
        json={"recipient_name": "Otra", "address": "Otra calle"},
    )
    assert again.status_code == 409
    assert again.json()["detail"] == "delivery_exists"
    assert shop.store.get_customer(PILOT_TENANT_ID, customer.id).name == "Lucía"

    kept_post = client.post(
        f"/api/orders/{kept_order.id}/delivery",
        json={"recipient_name": "Lucía", "address": "Calle 9"},
    )
    assert kept_post.status_code == 200
    assert kept_post.json()["customer"]["name"] == "Ana"
    assert kept_post.json()["customer"]["address"] == "Zona Norte"
    assert kept_post.json()["delivery"]["address"] == "Calle 9"
    untouched = shop.store.get_customer(PILOT_TENANT_ID, kept.id)
    assert untouched is not None
    assert untouched.name == "Ana"
    assert untouched.address == "Zona Norte"


def test_manual_delivery_without_confirmed_payment() -> None:
    shop = make_shop()
    customer = shop.store.get_or_create_customer(PILOT_TENANT_ID, "59170003003")
    unpaid = shop.store.create_order(
        PILOT_TENANT_ID,
        customer.id,
        OrderItem("h001-M-VP", "blusa de hilo", 1, Decimal("145.00"), "BOB"),
    )
    client = owner_client(shop)
    missing_payment = client.post(
        f"/api/orders/{unpaid.id}/delivery",
        json={"recipient_name": "Lucía", "address": "Calle 9"},
    )
    assert missing_payment.status_code == 409
    assert missing_payment.json()["detail"] == "payment_not_confirmed"
    assert shop.store.delivery_for_order(PILOT_TENANT_ID, unpaid.id) is None

    _customer, pending_order = _paid_order(shop, "59170003004", confirm=False)
    pending = client.post(
        f"/api/orders/{pending_order.id}/delivery",
        json={"recipient_name": "Lucía", "address": "Calle 9"},
    )
    assert pending.status_code == 409
    assert pending.json()["detail"] == "payment_not_confirmed"
    assert shop.store.delivery_for_order(PILOT_TENANT_ID, pending_order.id) is None
    still = shop.store.payment_for_order(PILOT_TENANT_ID, pending_order.id)
    assert still is not None
    assert still.status is PaymentStatus.PENDING


def test_orders_search_filters_by_phone_name_or_public_number() -> None:
    shop = make_shop()
    _ana, ana_order = _paid_order(shop, "59170003111", name="Ana Rojas")
    _luis, luis_order = _paid_order(shop, "59170003222", name="Luis")
    client = owner_client(shop)

    def ids_for(q: str) -> set[str]:
        response = client.get("/api/orders", params={"q": q})
        assert response.status_code == 200
        return {row["id"] for row in response.json()["orders"]}

    assert ids_for("") == {str(ana_order.id), str(luis_order.id)}
    assert ids_for("  ") == {str(ana_order.id), str(luis_order.id)}
    assert ids_for("59170003111") == {str(ana_order.id)}
    assert ids_for(ana_order.public_number or "") == {str(ana_order.id)}
    assert ids_for("ana") == {str(ana_order.id)}
    assert ids_for(str(luis_order.id)[:8]) == {str(luis_order.id)}

    bare = client.get("/api/orders").json()["orders"]
    row = next(item for item in bare if item["id"] == str(ana_order.id))
    assert row["has_delivery"] is False
    assert row["delivery"] is None
