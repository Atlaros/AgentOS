"""T2 Contabilidad: period filter + hydrated ledger rows (ADR-010)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from factory_os.domain.ledger import sync_facts
from factory_os.domain.models import CashMovement
from tests.conftest import make_shop, owner_client


def test_default_month_excludes_previous_month_entry() -> None:
    shop = make_shop()
    client = owner_client(shop)
    client.post("/api/cash/session/open", json={"opening_float": "0"})

    posted = client.post(
        "/api/cash",
        json={
            "direction": "in",
            "amount": "40",
            "reason": "venta vieja",
            "category": "venta",
            "method": "cash",
        },
    )
    assert posted.status_code == 200
    movement_id = posted.json()["id"]

    sync_facts(shop.store, shop.store.tenant_id)
    for entry in shop.store.list_ledger(shop.store.tenant_id):
        if entry.source == "cash" and str(entry.source_id) == movement_id:
            entry.created_at = datetime(2020, 1, 15, 12, 0, tzinfo=UTC)
            break
    else:
        raise AssertionError("expected cash ledger entry")

    body = client.get("/api/ledger").json()
    assert body["period"]["preset"] == "month"
    assert all(row["source_id"] != movement_id for row in body["entries"])
    assert Decimal(body["in"]) == Decimal("0")


def test_hydrated_cash_entry_includes_category_and_method() -> None:
    shop = make_shop()
    client = owner_client(shop)
    client.post("/api/cash/session/open", json={"opening_float": "0"})

    posted = client.post(
        "/api/cash",
        json={
            "direction": "in",
            "amount": "25",
            "reason": "venta mostrador",
            "category": "venta",
            "method": "cash",
        },
    )
    assert posted.status_code == 200
    movement_id = posted.json()["id"]

    body = client.get("/api/ledger?period=month").json()
    cash_rows = [row for row in body["entries"] if row["source_id"] == movement_id]
    assert len(cash_rows) == 1
    row = cash_rows[0]
    assert row["category"] == "venta"
    assert row["method"] == "cash"
    assert row["reference_label"]
    assert row["reference_href"] == "/cash?tab=movements"


def test_voided_entry_listed_but_excluded_from_period_totals() -> None:
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
        created_at=datetime.now(UTC),
    )
    shop.store.cash[movement.id] = movement

    sync_facts(shop.store, tenant)
    client = owner_client(shop)
    body = client.get("/api/ledger?period=month").json()

    assert any(
        row["source_id"] == str(movement.id) and row["status"] == "voided"
        for row in body["entries"]
    )
    assert Decimal(body["in"]) == Decimal("0")
    assert Decimal(body["out"]) == Decimal("0")
    assert Decimal(body["balance"]) == Decimal("0")
