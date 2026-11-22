"""T3 Contabilidad: GET /api/journal + CSV/PDF export (ADR-011)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from tests.conftest import make_shop, owner_client


def test_cash_venta_appears_in_journal_api() -> None:
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
    mid = posted.json()["id"]

    body = client.get("/api/journal?period=month").json()
    assert "period" in body
    assert body["period"]["preset"] == "month"
    matches = [
        row
        for row in body["entries"]
        if row["origin_source"] == "cash" and row["origin_id"] == mid and row["kind"] == "post"
    ]
    assert len(matches) == 1
    entry = matches[0]
    assert entry["memo"]
    assert len(entry["lines"]) == 2
    codes = {line["direction"]: line["account_code"] for line in entry["lines"]}
    assert codes["debit"] == "1100"
    assert codes["credit"] == "4100"
    for line in entry["lines"]:
        assert line["account_name"]
        assert Decimal(line["amount"]) == Decimal("100")
        assert line["currency"] == "BOB"
    assert entry.get("origin_href") == "/cash?tab=movements"


def test_void_cash_adds_reverse_in_journal_api() -> None:
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
    mid = posted.json()["id"]
    voided = client.post(f"/api/cash/{mid}/void", json={"reason": "duplicado"})
    assert voided.status_code == 200

    body = client.get("/api/journal?period=month").json()
    kinds = {
        row["kind"]
        for row in body["entries"]
        if row["origin_source"] == "cash" and row["origin_id"] == mid
    }
    assert kinds == {"post", "reverse"}


def test_journal_export_csv_pdf_and_xlsx() -> None:
    shop = make_shop()
    client = owner_client(shop)
    client.post("/api/cash/session/open", json={"opening_float": "0"})
    posted = client.post(
        "/api/cash",
        json={
            "direction": "in",
            "amount": "40",
            "reason": "venta",
            "category": "venta",
            "method": "cash",
        },
    )
    assert posted.status_code == 200

    csv_res = client.get("/api/journal/export", params={"format": "csv", "period": "month"})
    assert csv_res.status_code == 200
    assert "text/csv" in csv_res.headers.get("content-type", "")
    disposition = csv_res.headers.get("content-disposition", "")
    assert "attachment" in disposition
    assert ".csv" in disposition
    assert "agentia" not in disposition.lower()
    assert "diario" in disposition.lower()
    # Spanish column header appears after the metadata block.
    assert "fecha,asiento,cuenta,descripción,debe,haber,origen" in csv_res.text.replace("\r\n", "\n")
    assert "cash" in csv_res.text
    assert "1100" in csv_res.text

    pdf_res = client.get("/api/journal/export", params={"format": "pdf", "period": "month"})
    assert pdf_res.status_code == 200
    assert "application/pdf" in pdf_res.headers.get("content-type", "")
    assert ".pdf" in pdf_res.headers.get("content-disposition", "")
    assert pdf_res.content[:4] == b"%PDF"

    xlsx_res = client.get("/api/journal/export", params={"format": "xlsx", "period": "month"})
    assert xlsx_res.status_code == 200
    assert "spreadsheetml" in xlsx_res.headers.get("content-type", "")
    assert ".xlsx" in xlsx_res.headers.get("content-disposition", "")

    bad = client.get("/api/journal/export", params={"format": "docx"})
    assert bad.status_code == 400
    assert bad.json()["detail"] == "bad_format"


def test_journal_period_excludes_old_entry() -> None:
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
    mid = UUID(posted.json()["id"])

    entry = shop.store.get_journal_by_origin(shop.store.tenant_id, "cash", mid, "post")
    assert entry is not None
    entry.entry_at = datetime(2020, 1, 15, 12, 0, tzinfo=UTC)

    body = client.get("/api/journal").json()
    assert body["period"]["preset"] == "month"
    assert all(row["origin_id"] != str(mid) for row in body["entries"])
