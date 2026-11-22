"""T4 ADR-012: purchase-order lifecycle, partial receive, and supplier payments."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from factory_os.domain.journal import assert_journal_balanced, sum_by_direction
from factory_os.domain.models import PILOT_TENANT_ID
from tests.conftest import make_shop, owner_client

SKU = "h001-M-VP"


def _codes(lines) -> dict[str, str]:
    return {line.direction: (line.account_code or "") for line in lines}


def _journal_ids(shop) -> set[UUID]:
    return {entry.id for entry in shop.store.list_journal_entries(PILOT_TENANT_ID)}


def _create_draft(client, supplier_id: UUID, *, quantity: int = 2, unit_cost: str = "10"):
    created = client.post(
        "/api/purchase-orders",
        json={
            "supplier_id": str(supplier_id),
            "notes": "pedido t4",
            "lines": [{"variant_sku": SKU, "quantity": quantity, "unit_cost": unit_cost}],
        },
    )
    assert created.status_code == 200
    body = created.json()
    assert body["status"] == "draft"
    assert body["payment_status"] == "unpaid"
    assert Decimal(body["amount_paid"]) == Decimal("0")
    return body


def test_draft_can_be_sent_and_another_draft_cancelled() -> None:
    shop = make_shop()
    client = owner_client(shop)
    supplier = shop.store.create_supplier(PILOT_TENANT_ID, name="Textiles Andinos")

    sent_body = _create_draft(client, supplier.id)
    sent = client.patch(
        f"/api/purchase-orders/{sent_body['id']}",
        json={"status": "sent"},
    )
    assert sent.status_code == 200
    assert sent.json()["status"] == "sent"
    assert sent.json()["payment_status"] == "unpaid"

    draft = _create_draft(client, supplier.id, quantity=1)
    cancelled = client.patch(
        f"/api/purchase-orders/{draft['id']}",
        json={"status": "cancelled"},
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    listed = client.get("/api/purchase-orders")
    assert listed.status_code == 200
    by_id = {row["id"]: row for row in listed.json()["purchase_orders"]}
    assert by_id[sent_body["id"]]["status"] == "sent"
    assert by_id[draft["id"]]["status"] == "cancelled"


def test_receive_total_from_sent_posts_journal_and_links_receipt() -> None:
    shop = make_shop()
    client = owner_client(shop)
    supplier = shop.store.create_supplier(PILOT_TENANT_ID, name="Calzados Sur")
    record = shop.store.get_variant(PILOT_TENANT_ID, SKU)
    assert record is not None
    stock_before = record.stock

    order = _create_draft(client, supplier.id, quantity=2, unit_cost="12")
    before = _journal_ids(shop)
    sent = client.patch(
        f"/api/purchase-orders/{order['id']}",
        json={"status": "sent"},
    )
    assert sent.status_code == 200
    assert _journal_ids(shop) == before

    fresh = _create_draft(client, supplier.id, quantity=1, unit_cost="12")
    still_draft = client.post(
        f"/api/purchase-orders/{fresh['id']}/receive",
        json={"lines": [{"variant_sku": SKU, "quantity": 1}], "payment_method": "credit"},
    )
    assert still_draft.status_code == 400

    received = client.post(
        f"/api/purchase-orders/{order['id']}/receive",
        json={
            "lines": [{"variant_sku": SKU, "quantity": 2}],
            "payment_method": "credit",
        },
    )
    assert received.status_code == 200
    body = received.json()
    assert body["status"] == "received"
    assert body["lines"][0]["quantity_received"] == 2
    assert shop.store.get_variant(PILOT_TENANT_ID, SKU).stock == stock_before + 2

    order_id = UUID(order["id"])
    receipts = [
        item
        for item in shop.store.list_purchases(PILOT_TENANT_ID)
        if item.purchase_order_id == order_id
    ]
    assert len(receipts) == 1
    assert receipts[0].quantity == 2
    assert receipts[0].supplier_id == supplier.id

    new_entries = [
        entry
        for entry in shop.store.list_journal_entries(PILOT_TENANT_ID)
        if entry.id not in before
    ]
    assert len(new_entries) == 1
    assert new_entries[0].origin_source == "purchase"
    assert new_entries[0].origin_id == receipts[0].id
    assert_journal_balanced(new_entries[0].lines)


def test_partial_receive_then_complete() -> None:
    shop = make_shop()
    client = owner_client(shop)
    supplier = shop.store.create_supplier(PILOT_TENANT_ID, name="Parciales")
    record = shop.store.get_variant(PILOT_TENANT_ID, SKU)
    assert record is not None
    stock_before = record.stock
    order = _create_draft(client, supplier.id, quantity=4, unit_cost="8")
    sent = client.patch(
        f"/api/purchase-orders/{order['id']}",
        json={"status": "sent"},
    )
    assert sent.status_code == 200

    first = client.post(
        f"/api/purchase-orders/{order['id']}/receive",
        json={
            "lines": [{"variant_sku": SKU, "quantity": 1, "unit_cost": "8"}],
            "payment_method": "credit",
        },
    )
    assert first.status_code == 200
    assert first.json()["status"] == "partially_received"
    assert first.json()["lines"][0]["quantity_received"] == 1
    assert first.json()["payment_status"] == "unpaid"

    second = client.post(
        f"/api/purchase-orders/{order['id']}/receive",
        json={
            "lines": [{"variant_sku": SKU, "quantity": 3}],
            "payment_method": "credit",
        },
    )
    assert second.status_code == 200
    assert second.json()["status"] == "received"
    assert second.json()["lines"][0]["quantity_received"] == 4
    assert shop.store.get_variant(PILOT_TENANT_ID, SKU).stock == stock_before + 4


def test_credit_receive_then_transfer_settles_cxp() -> None:
    shop = make_shop()
    client = owner_client(shop)
    supplier = shop.store.create_supplier(PILOT_TENANT_ID, name="Crédito Andes")
    order = _create_draft(client, supplier.id, quantity=2, unit_cost="15")
    assert client.patch(
        f"/api/purchase-orders/{order['id']}",
        json={"status": "sent"},
    ).status_code == 200

    received = client.post(
        f"/api/purchase-orders/{order['id']}/receive",
        json={
            "lines": [{"variant_sku": SKU, "quantity": 2, "unit_cost": "15"}],
            "payment_method": "credit",
        },
    )
    assert received.status_code == 200
    assert received.json()["payment_status"] == "unpaid"
    assert Decimal(received.json()["amount_paid"]) == Decimal("0")

    order_id = UUID(order["id"])
    receipt = next(
        item
        for item in shop.store.list_purchases(PILOT_TENANT_ID)
        if item.purchase_order_id == order_id
    )
    purchase = shop.store.get_journal_by_origin(
        PILOT_TENANT_ID, "purchase", receipt.id, "post"
    )
    assert purchase is not None
    assert_journal_balanced(purchase.lines)
    purchase_codes = _codes(purchase.lines)
    assert purchase_codes["debit"] == "1300"
    assert purchase_codes["credit"] == "2100"
    assert sum_by_direction(purchase.lines, "debit") == Decimal("30.00")

    cash_before = len(shop.store.list_cash(PILOT_TENANT_ID))
    paid = client.post(
        f"/api/purchase-orders/{order['id']}/payments",
        json={"amount": "30", "method": "transfer", "currency": "BOB"},
    )
    assert paid.status_code == 200
    assert paid.json()["payment_status"] == "paid"
    assert Decimal(paid.json()["amount_paid"]) == Decimal("30.00")
    assert len(shop.store.list_cash(PILOT_TENANT_ID)) == cash_before

    settlements = [
        entry
        for entry in shop.store.list_journal_entries(PILOT_TENANT_ID)
        if entry.origin_source == "supplier_payment"
    ]
    assert len(settlements) == 1
    assert_journal_balanced(settlements[0].lines)
    settle_codes = _codes(settlements[0].lines)
    assert settle_codes["debit"] == "2100"
    assert settle_codes["credit"] == "1200"
    assert sum_by_direction(settlements[0].lines, "debit") == Decimal("30.00")
    assert "5100" not in {line.account_code for line in settlements[0].lines}


def test_cash_receive_from_po_covers_payment_with_inventario_caja() -> None:
    shop = make_shop()
    client = owner_client(shop)
    supplier = shop.store.create_supplier(PILOT_TENANT_ID, name="Contado")
    order = _create_draft(client, supplier.id, quantity=1, unit_cost="20")
    before = _journal_ids(shop)
    assert client.patch(
        f"/api/purchase-orders/{order['id']}",
        json={"status": "sent"},
    ).status_code == 200

    received = client.post(
        f"/api/purchase-orders/{order['id']}/receive",
        json={
            "lines": [{"variant_sku": SKU, "quantity": 1, "unit_cost": "20"}],
            "payment_method": "cash",
        },
    )
    assert received.status_code == 200
    body = received.json()
    assert body["status"] == "received"
    assert body["payment_status"] == "paid"
    assert Decimal(body["amount_paid"]) == Decimal("20.00")

    order_id = UUID(order["id"])
    receipt = next(
        item
        for item in shop.store.list_purchases(PILOT_TENANT_ID)
        if item.purchase_order_id == order_id
    )
    assert receipt.payment_method == "cash"
    entry = shop.store.get_journal_by_origin(
        PILOT_TENANT_ID, "purchase", receipt.id, "post"
    )
    assert entry is not None
    assert_journal_balanced(entry.lines)
    codes = _codes(entry.lines)
    assert codes["debit"] == "1300"
    assert codes["credit"] == "1100"
    assert sum_by_direction(entry.lines, "debit") == Decimal("20.00")
    new_sources = {
        item.origin_source
        for item in shop.store.list_journal_entries(PILOT_TENANT_ID)
        if item.id not in before
    }
    assert new_sources == {"purchase"}


def test_cannot_over_receive_or_receive_cancelled() -> None:
    shop = make_shop()
    client = owner_client(shop)
    supplier = shop.store.create_supplier(PILOT_TENANT_ID, name="Tope")
    record = shop.store.get_variant(PILOT_TENANT_ID, SKU)
    assert record is not None
    stock_before = record.stock

    order = _create_draft(client, supplier.id, quantity=2, unit_cost="9")
    assert client.patch(
        f"/api/purchase-orders/{order['id']}",
        json={"status": "sent"},
    ).status_code == 200
    over = client.post(
        f"/api/purchase-orders/{order['id']}/receive",
        json={
            "lines": [{"variant_sku": SKU, "quantity": 3, "unit_cost": "9"}],
            "payment_method": "credit",
        },
    )
    assert over.status_code == 400
    assert shop.store.get_variant(PILOT_TENANT_ID, SKU).stock == stock_before
    detail = client.get(f"/api/purchase-orders/{order['id']}")
    assert detail.json()["status"] == "sent"
    assert detail.json()["lines"][0]["quantity_received"] == 0

    cancelled_order = _create_draft(client, supplier.id, quantity=1, unit_cost="9")
    assert client.patch(
        f"/api/purchase-orders/{cancelled_order['id']}",
        json={"status": "sent"},
    ).status_code == 200
    assert client.patch(
        f"/api/purchase-orders/{cancelled_order['id']}",
        json={"status": "cancelled"},
    ).status_code == 200
    denied = client.post(
        f"/api/purchase-orders/{cancelled_order['id']}/receive",
        json={
            "lines": [{"variant_sku": SKU, "quantity": 1, "unit_cost": "9"}],
            "payment_method": "cash",
        },
    )
    assert denied.status_code == 400
    assert shop.store.get_variant(PILOT_TENANT_ID, SKU).stock == stock_before
