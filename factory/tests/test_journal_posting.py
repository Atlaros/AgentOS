"""T2 Contabilidad: automatic journal posting + reverse on void (ADR-011)."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

from factory_os.domain.journal import assert_journal_balanced, sum_by_direction
from factory_os.domain.journal_posting import sync_journal
from factory_os.domain.ledger import remember_cash, sync_facts
from factory_os.domain.models import Payment, PaymentStatus, PILOT_TENANT_ID
from tests.conftest import make_shop, owner_client


def _codes(lines) -> dict[str, str]:
    return {line.direction: (line.account_code or "") for line in lines}


def test_cash_venta_in_posts_caja_ventas() -> None:
    shop = make_shop()
    client = owner_client(shop)
    client.post("/api/cash/session/open", json={"opening_float": "0"})
    posted = client.post(
        "/api/cash",
        json={
            "direction": "in",
            "amount": "100",
            "reason": "venta mostrador",
            "category": "venta",
            "method": "cash",
        },
    )
    assert posted.status_code == 200
    mid = UUID(posted.json()["id"])

    entry = shop.store.get_journal_by_origin(PILOT_TENANT_ID, "cash", mid, "post")
    assert entry is not None
    assert len(entry.lines) == 2
    assert_journal_balanced(entry.lines)
    assert sum_by_direction(entry.lines, "debit") == Decimal("100")
    by_dir = _codes(entry.lines)
    assert by_dir["debit"] == "1100"
    assert by_dir["credit"] == "4100"


def test_void_cash_creates_reverse_journal() -> None:
    shop = make_shop()
    client = owner_client(shop)
    client.post("/api/cash/session/open", json={"opening_float": "0"})
    posted = client.post(
        "/api/cash",
        json={
            "direction": "in",
            "amount": "50",
            "reason": "venta",
            "category": "venta",
            "method": "cash",
        },
    )
    mid = UUID(posted.json()["id"])
    voided = client.post(f"/api/cash/{mid}/void", json={"reason": "duplicado"})
    assert voided.status_code == 200

    post = shop.store.get_journal_by_origin(PILOT_TENANT_ID, "cash", mid, "post")
    reverse = shop.store.get_journal_by_origin(PILOT_TENANT_ID, "cash", mid, "reverse")
    assert post is not None
    assert reverse is not None
    assert reverse.reverses_entry_id == post.id
    assert_journal_balanced(reverse.lines)
    post_codes = _codes(post.lines)
    reverse_codes = _codes(reverse.lines)
    assert reverse_codes["debit"] == post_codes["credit"]
    assert reverse_codes["credit"] == post_codes["debit"]


def test_confirmed_non_cash_payment_posts_banco_ventas() -> None:
    shop = make_shop()
    tenant = shop.store.tenant_id
    payment = Payment(
        id=uuid4(),
        tenant_id=tenant,
        order_id=None,
        provider="fake",
        provider_ref=f"pay-{uuid4().hex[:8]}",
        amount=Decimal("80.00"),
        currency="BOB",
        status=PaymentStatus.PENDING,
        qr_payload="QR:test",
    )
    shop.store.payments[payment.id] = payment
    shop.store.payments_by_ref[payment.provider_ref] = payment
    shop.store.confirm_from_adapter(payment.provider_ref)

    entry = shop.store.get_journal_by_origin(tenant, "payment", payment.id, "post")
    assert entry is not None
    assert_journal_balanced(entry.lines)
    by_dir = _codes(entry.lines)
    assert by_dir["debit"] == "1200"
    assert by_dir["credit"] == "4100"
    assert sum_by_direction(entry.lines, "debit") == Decimal("80.00")


def test_receive_purchase_posts_inventario_caja() -> None:
    shop = make_shop()
    client = owner_client(shop)
    received = client.post(
        "/api/stock/receive",
        json={"variant_sku": "h001-M-VP", "quantity": 2, "unit_cost": "15"},
    )
    assert received.status_code == 200
    receipt_id = UUID(received.json()["purchase_id"])

    entry = shop.store.get_journal_by_origin(PILOT_TENANT_ID, "purchase", receipt_id, "post")
    assert entry is not None
    assert_journal_balanced(entry.lines)
    by_dir = _codes(entry.lines)
    assert by_dir["debit"] == "1300"
    assert by_dir["credit"] == "1100"
    assert sum_by_direction(entry.lines, "debit") == Decimal("30.00")


def test_double_remember_cash_does_not_duplicate_posts() -> None:
    shop = make_shop()
    client = owner_client(shop)
    client.post("/api/cash/session/open", json={"opening_float": "0"})
    posted = client.post(
        "/api/cash",
        json={
            "direction": "in",
            "amount": "20",
            "reason": "venta",
            "category": "venta",
            "method": "cash",
        },
    )
    mid = UUID(posted.json()["id"])
    movement = shop.store.get_cash_movement(PILOT_TENANT_ID, mid)
    assert movement is not None
    remember_cash(shop.store, movement)
    remember_cash(shop.store, movement)
    sync_journal(shop.store, PILOT_TENANT_ID)
    sync_facts(shop.store, PILOT_TENANT_ID)

    posts = [
        entry
        for entry in shop.store.list_journal_entries(PILOT_TENANT_ID)
        if entry.origin_id == mid and entry.kind == "post"
    ]
    assert len(posts) == 1
