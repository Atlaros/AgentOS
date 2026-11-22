"""T3 Contabilidad: CSV/PDF export + breakdown by source (ADR-010)."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from factory_os.domain.ledger import sync_facts
from factory_os.domain.models import CashMovement, Payment, PaymentStatus
from tests.conftest import make_shop, owner_client


def _seed_mixed_sources(shop, client) -> None:
    """Cash sale + confirmed non-cash payment + purchase with unit cost."""
    client.post("/api/cash/session/open", json={"opening_float": "0"})
    cash = client.post(
        "/api/cash",
        json={
            "direction": "in",
            "amount": "40",
            "reason": "venta mostrador",
            "category": "venta",
            "method": "cash",
        },
    )
    assert cash.status_code == 200

    tenant = shop.store.tenant_id
    payment = Payment(
        id=uuid4(),
        tenant_id=tenant,
        order_id=None,
        provider="fake",
        provider_ref=f"pay-{uuid4().hex[:8]}",
        amount=Decimal("25.00"),
        currency="BOB",
        status=PaymentStatus.CONFIRMED,
        qr_payload="QR:test",
    )
    shop.store.payments[payment.id] = payment
    shop.store.payments_by_ref[payment.provider_ref] = payment

    received = client.post(
        "/api/stock/receive",
        json={"variant_sku": "h001-M-VP", "quantity": 1, "unit_cost": "10"},
    )
    assert received.status_code == 200
    sync_facts(shop.store, tenant)


def test_ledger_includes_breakdown_by_source() -> None:
    shop = make_shop()
    client = owner_client(shop)
    _seed_mixed_sources(shop, client)

    body = client.get("/api/ledger?period=month").json()
    breakdown = body["breakdown"]
    assert set(breakdown) >= {"payment", "cash", "purchase"}
    assert Decimal(breakdown["cash"]["in"]) == Decimal("40")
    assert Decimal(breakdown["cash"]["out"]) == Decimal("0")
    assert Decimal(breakdown["cash"]["balance"]) == Decimal("40")
    assert Decimal(breakdown["payment"]["in"]) == Decimal("25")
    assert Decimal(breakdown["payment"]["balance"]) == Decimal("25")
    assert Decimal(breakdown["purchase"]["out"]) == Decimal("10")
    assert Decimal(breakdown["purchase"]["balance"]) == Decimal("-10")


def test_breakdown_excludes_voided_cash() -> None:
    shop = make_shop()
    tenant = shop.store.tenant_id
    client = owner_client(shop)
    client.post("/api/cash/session/open", json={"opening_float": "0"})

    live = client.post(
        "/api/cash",
        json={
            "direction": "in",
            "amount": "20",
            "reason": "vigente",
            "category": "venta",
            "method": "cash",
        },
    )
    assert live.status_code == 200

    voided = CashMovement(
        id=uuid4(),
        tenant_id=tenant,
        direction="in",
        amount=Decimal("99.00"),
        currency="BOB",
        reason="anulado",
        status="voided",
        category="ajuste",
        method="cash",
    )
    shop.store.cash[voided.id] = voided
    sync_facts(shop.store, tenant)

    body = client.get("/api/ledger?period=month").json()
    cash = body["breakdown"]["cash"]
    assert Decimal(cash["in"]) == Decimal("20")
    assert Decimal(cash["balance"]) == Decimal("20")


def test_ledger_export_csv_and_pdf() -> None:
    shop = make_shop()
    client = owner_client(shop)
    _seed_mixed_sources(shop, client)

    csv_res = client.get(
        "/api/ledger/export",
        params={"format": "csv", "period": "month", "source": "cash"},
    )
    assert csv_res.status_code == 200
    assert "text/csv" in csv_res.headers.get("content-type", "")
    assert "attachment" in csv_res.headers.get("content-disposition", "")
    assert "ledger_export.csv" in csv_res.headers.get("content-disposition", "")
    header = csv_res.text.splitlines()[0]
    for column in (
        "created_at",
        "source",
        "source_id",
        "reference_label",
        "category",
        "method",
        "direction",
        "amount",
        "currency",
        "status",
    ):
        assert column in header
    data_lines = csv_res.text.splitlines()[1:]
    assert data_lines
    assert all(",cash," in line for line in data_lines)
    assert all(",payment," not in line for line in data_lines)
    assert "venta" in csv_res.text

    pdf_res = client.get("/api/ledger/export", params={"format": "pdf", "period": "month"})
    assert pdf_res.status_code == 200
    assert "application/pdf" in pdf_res.headers.get("content-type", "")
    assert "ledger_export.pdf" in pdf_res.headers.get("content-disposition", "")
    assert pdf_res.content[:4] == b"%PDF"

    xlsx_res = client.get("/api/ledger/export", params={"format": "xlsx", "period": "month"})
    assert xlsx_res.status_code == 200

    bad = client.get("/api/ledger/export", params={"format": "docx"})
    assert bad.status_code == 400
    assert bad.json()["detail"] == "bad_format"
