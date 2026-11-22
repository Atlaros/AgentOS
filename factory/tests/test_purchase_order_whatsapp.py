"""ADR-012 amendment: preview/confirm WhatsApp send for supplier purchase orders."""

from __future__ import annotations

from uuid import UUID

from factory_os.domain.models import PILOT_TENANT_ID
from factory_os.domain.purchase_order_whatsapp import (
    confirm_send_purchase_order,
    format_purchase_order_message,
    resolve_supplier_wa_number,
)
from factory_os.tools.channel import FakeChannel
from tests.conftest import make_shop, owner_client
from tests.test_suppliers_orders import SKU, _create_draft


def test_resolve_supplier_wa_number_prefers_whatsapp() -> None:
    class _Supplier:
        whatsapp = "591 7000 0001"
        phone = "59171111111"

    assert resolve_supplier_wa_number(_Supplier()) == "59170000001"


def test_format_purchase_order_message_spanish_summary() -> None:
    body = format_purchase_order_message(
        {
            "number": "PO-ABCDEF12",
            "notes": "urgente",
            "lines": [
                {
                    "variant_sku": "h001-M-VP",
                    "name": "Camisa",
                    "quantity_ordered": 3,
                    "unit_cost": "10.50",
                }
            ],
        }
    )
    assert "PO-ABCDEF12" in body
    assert "h001-M-VP" in body
    assert "3 u." in body
    assert "10.50" in body or "31.50" in body


def test_preview_ok_for_draft_with_number() -> None:
    shop = make_shop()
    client = owner_client(shop)
    supplier = shop.store.create_supplier(
        PILOT_TENANT_ID,
        name="Distribuidora Norte",
        whatsapp="59172223333",
    )
    order = _create_draft(client, supplier.id)

    preview = client.post(
        f"/api/purchase-orders/{order['id']}/send-whatsapp",
        json={"confirm": False},
    )
    assert preview.status_code == 200
    body = preview.json()
    assert body["can_send"] is True
    assert body["wa_number"] == "59172223333"
    assert "Pedido de compra" in body["body"]
    assert body["order_id"] == order["id"]


def test_confirm_sends_and_marks_sent() -> None:
    shop = make_shop()
    channel = FakeChannel()
    shop.channel = channel
    client = owner_client(shop)
    supplier = shop.store.create_supplier(
        PILOT_TENANT_ID,
        name="Proveedor WA",
        whatsapp="59173334444",
    )
    order = _create_draft(client, supplier.id)

    confirm = client.post(
        f"/api/purchase-orders/{order['id']}/send-whatsapp",
        json={"confirm": True},
    )
    assert confirm.status_code == 200
    payload = confirm.json()
    assert payload["sent"] is True
    assert payload["purchase_order"]["status"] == "sent"
    assert len(channel.sent) == 1
    assert channel.sent[0][0] == "59173334444"


def test_missing_number_fails_and_stays_draft() -> None:
    shop = make_shop()
    client = owner_client(shop)
    supplier = shop.store.create_supplier(PILOT_TENANT_ID, name="Sin contacto")
    order = _create_draft(client, supplier.id)

    preview = client.post(
        f"/api/purchase-orders/{order['id']}/send-whatsapp",
        json={"confirm": False},
    )
    assert preview.status_code == 200
    assert preview.json()["can_send"] is False

    confirm = client.post(
        f"/api/purchase-orders/{order['id']}/send-whatsapp",
        json={"confirm": True},
    )
    assert confirm.status_code == 400
    assert confirm.json()["detail"] == "supplier_number_missing"
    stored = shop.store.get_purchase_order(PILOT_TENANT_ID, UUID(order["id"]))
    assert stored is not None
    assert stored.status == "draft"


def test_channel_raise_keeps_draft() -> None:
    shop = make_shop()
    channel = FakeChannel()
    shop.channel = channel
    client = owner_client(shop)
    supplier = shop.store.create_supplier(
        PILOT_TENANT_ID,
        name="Proveedor frágil",
        phone="59175556666",
    )
    order = _create_draft(client, supplier.id)

    def _boom(_wa: str, _text: str) -> None:
        raise RuntimeError("meta_rejected")

    channel.send_text = _boom  # type: ignore[method-assign]

    confirm = client.post(
        f"/api/purchase-orders/{order['id']}/send-whatsapp",
        json={"confirm": True},
    )
    assert confirm.status_code == 400
    assert confirm.json()["detail"] == "send_failed"
    oid = UUID(order["id"])
    assert shop.store.get_purchase_order(PILOT_TENANT_ID, oid).status == "draft"


def test_domain_confirm_uses_template_when_configured() -> None:
    shop = make_shop()
    channel = FakeChannel()
    supplier = shop.store.create_supplier(
        PILOT_TENANT_ID,
        name="Template Co",
        whatsapp="59178889999",
    )
    order = shop.store.create_purchase_order(
        PILOT_TENANT_ID,
        supplier.id,
        [{"variant_sku": SKU, "quantity": 1, "unit_cost": None, "currency": "BOB"}],
        status="draft",
        notes="",
    )
    result = confirm_send_purchase_order(
        shop.store,
        PILOT_TENANT_ID,
        order.id,
        channel,
        template_name="pedido_proveedor_oc",
        template_lang="es",
    )
    assert result["sent"] is True
    assert len(channel.templates) == 1
    assert channel.templates[0]["name"] == "pedido_proveedor_oc"
    params = channel.templates[0]["body_parameters"]
    assert len(params) == 3
    assert params[1]  # order number
    assert "x1" in params[2] or "x" in params[2]


def test_preview_rejects_non_draft() -> None:
    shop = make_shop()
    client = owner_client(shop)
    supplier = shop.store.create_supplier(PILOT_TENANT_ID, name="X", whatsapp="5917")
    order = _create_draft(client, supplier.id)
    client.patch(f"/api/purchase-orders/{order['id']}", json={"status": "sent"})
    bad = client.post(
        f"/api/purchase-orders/{order['id']}/send-whatsapp",
        json={"confirm": False},
    )
    assert bad.status_code == 400
    assert bad.json()["detail"] == "bad_status"