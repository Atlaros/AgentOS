"""T1 Contabilidad: soft-voided cash must stop counting in ledger totals (ADR-010)."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from factory_os.domain.ledger import sync_facts
from factory_os.domain.models import CashMovement
from tests.conftest import make_shop, owner_client


def test_voided_cash_stops_counting_in_ledger_totals() -> None:
    shop = make_shop()
    client = owner_client(shop)
    client.post("/api/cash/session/open", json={"opening_float": "0"})

    posted = client.post(
        "/api/cash",
        json={
            "direction": "in",
            "amount": "50",
            "reason": "venta mostrador",
            "category": "venta",
            "method": "cash",
        },
    )
    assert posted.status_code == 200
    movement_id = posted.json()["id"]

    ledger = client.get("/api/ledger").json()
    cash_rows = [row for row in ledger["entries"] if row["source_id"] == movement_id]
    assert len(cash_rows) == 1
    assert cash_rows[0]["status"] == "recorded"
    assert Decimal(ledger["in"]) == Decimal("50")
    assert Decimal(ledger["balance"]) == Decimal("50")

    voided = client.post(
        f"/api/cash/{movement_id}/void",
        json={"reason": "duplicado"},
    )
    assert voided.status_code == 200
    assert voided.json()["status"] == "voided"

    after = client.get("/api/ledger").json()
    cash_rows = [row for row in after["entries"] if row["source_id"] == movement_id]
    assert len(cash_rows) == 1
    assert cash_rows[0]["status"] == "voided"
    assert Decimal(after["in"]) == Decimal("0")
    assert Decimal(after["out"]) == Decimal("0")
    assert Decimal(after["balance"]) == Decimal("0")


def test_sync_facts_marks_voided_cash_ledger_and_totals_exclude() -> None:
    shop = make_shop()
    tenant = shop.store.tenant_id
    movement = CashMovement(
        id=uuid4(),
        tenant_id=tenant,
        direction="in",
        amount=Decimal("30.00"),
        currency="BOB",
        reason="ajuste",
        status="voided",
        category="ajuste",
        method="cash",
    )
    shop.store.cash[movement.id] = movement

    sync_facts(shop.store, tenant)
    entries = shop.store.list_ledger(tenant)
    cash_rows = [row for row in entries if row.source == "cash" and row.source_id == movement.id]
    assert len(cash_rows) == 1
    assert cash_rows[0].status == "voided"

    client = owner_client(shop)
    body = client.get("/api/ledger").json()
    assert any(
        row["source_id"] == str(movement.id) and row["status"] == "voided"
        for row in body["entries"]
    )
    assert Decimal(body["in"]) == Decimal("0")
    assert Decimal(body["balance"]) == Decimal("0")
