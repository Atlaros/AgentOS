"""T2 Analista: narrative over analytics facts, with a deterministic fallback."""

from __future__ import annotations

from factory_os.agents.analyst import handle_analyst
from factory_os.api.main import create_app
from factory_os.contracts.employees import EmployeeRole, identity_for
from factory_os.domain.analytics_ask import answer_analytics_question
from factory_os.domain.models import PILOT_TENANT_ID
from factory_os.harness.model_gateway import DraftResult, FakeGateway
from fastapi.testclient import TestClient
from tests.conftest import api_settings, make_shop, owner_client


def _client(shop, secret: str) -> TestClient:
    client = TestClient(create_app(shop, api_settings()))
    client.headers["Authorization"] = f"Bearer {secret}"
    return client


def _staff(shop) -> TestClient:
    owner = owner_client(shop)
    created = owner.post(
        "/api/panel/users",
        json={
            "name": "Luis Staff",
            "email": "luis-ask@taller.local",
            "role": "staff",
            "secret": "staff-ask",
        },
    )
    assert created.status_code == 200
    return _client(shop, "staff-ask")


def test_fake_gateway_returns_fallback_and_facts() -> None:
    shop = make_shop()
    answered = answer_analytics_question(
        shop.store,
        PILOT_TENANT_ID,
        "¿Qué mirar primero?",
        FakeGateway(),
    )
    assert answered["used_fallback"] is True
    assert "Pedidos:" in answered["reply"]
    assert answered["facts"]["period"]["id"] == "7d"
    assert "orders" in answered["facts"]
    assert "alerts" in answered["facts"]


def test_staff_cannot_ask_analyst() -> None:
    shop = make_shop()
    staff = _staff(shop)
    denied = staff.post("/api/analytics/ask", json={"question": "¿Qué mirar primero?"})
    assert denied.status_code == 403

    owner = owner_client(shop)
    allowed = owner.post("/api/analytics/ask", json={"question": "¿Qué mirar primero?"})
    assert allowed.status_code == 200
    body = allowed.json()
    assert body["used_fallback"] is True
    assert "Pedidos:" in body["reply"]
    assert "facts" not in body


def test_empty_question_is_400() -> None:
    shop = make_shop()
    owner = owner_client(shop)
    empty = owner.post("/api/analytics/ask", json={"question": "   "})
    assert empty.status_code == 400


def test_grounded_stub_reply_is_used() -> None:
    shop = make_shop()

    class GroundedGateway:
        def staff_answer(self, *, system: str, user: str, fallback: str) -> DraftResult:
            assert "FACTS" in system or "hechos" in system.lower()
            assert "¿Qué mirar primero?" in user
            assert "Pedidos:" in fallback
            return DraftResult(
                text=(
                    "Mirá primero las alertas y entrá por el enlace a Proveedores "
                    "o a Reportes. No hay margen en estos hechos."
                ),
                provider="stub",
                used_fallback=False,
            )

    answered = answer_analytics_question(
        shop.store,
        PILOT_TENANT_ID,
        "¿Qué mirar primero?",
        GroundedGateway(),
    )
    assert answered["used_fallback"] is False
    assert "Proveedores" in answered["reply"]
    assert "Pedidos:" not in answered["reply"]


def test_invented_digits_use_fallback() -> None:
    shop = make_shop()

    class InventingGateway:
        def staff_answer(self, *, system: str, user: str, fallback: str) -> DraftResult:
            _ = (system, user, fallback)
            return DraftResult(
                text="El margen de la semana fue 999999 BOB y conviene reponer ya.",
                provider="stub",
                used_fallback=False,
            )

    answered = answer_analytics_question(
        shop.store,
        PILOT_TENANT_ID,
        "¿Cuál es el margen?",
        InventingGateway(),
    )
    assert answered["used_fallback"] is True
    assert "Pedidos:" in answered["reply"]
    assert "999999" not in answered["reply"]


def test_analyst_rejects_whatsapp() -> None:
    shop = make_shop()
    customer = shop.store.get_or_create_customer(PILOT_TENANT_ID, "59170007771")
    conversation = shop.store.get_or_create_conversation(PILOT_TENANT_ID, customer)
    conversation.state.channel = "whatsapp"
    identity = identity_for(EmployeeRole.ANALYST, PILOT_TENANT_ID)
    reply = handle_analyst(
        identity,
        shop.tools,
        conversation,
        "métricas del negocio",
        shop.gateway,
        store=shop.store,
    )
    assert "no atiende" in reply.lower()
    assert "Pedidos:" not in reply
