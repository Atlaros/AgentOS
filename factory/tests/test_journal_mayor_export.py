"""T2 Contabilidad export Fase A: Mayor xlsx + supervisor-only (ADR-011)."""

from __future__ import annotations

from io import BytesIO
from urllib.parse import urlencode

from openpyxl import load_workbook

from tests.conftest import make_shop, owner_client
from tests.test_journal_export_fase_a import EMPTY_NOTICE, _panel_client, _seed_cash_sale, _seed_roles

MAYOR_COLUMNS = ("fecha", "tipo", "memo", "debe", "haber", "saldo")


def test_staff_forbidden_on_mayor_xlsx_json_view_ok() -> None:
    shop = make_shop()
    owner = owner_client(shop)
    _seed_roles(owner)
    _seed_cash_sale(owner)

    staff = _panel_client(shop, "staff-journal-export")
    denied = staff.get("/api/journal/ledger", params={"format": "xlsx", "period": "month"})
    assert denied.status_code == 403

    # JSON screen view stays open to staff via require_human.
    assert staff.get("/api/journal/ledger", params={"period": "month"}).status_code == 200

    supervisor = _panel_client(shop, "super-journal-export")
    ok = supervisor.get("/api/journal/ledger", params={"format": "xlsx", "period": "month"})
    assert ok.status_code == 200
    assert "spreadsheetml" in ok.headers.get("content-type", "")

    owner_ok = owner.get("/api/journal/ledger", params={"format": "xlsx", "period": "month"})
    assert owner_ok.status_code == 200


def test_mayor_xlsx_spanish_header_running_balance_and_slug() -> None:
    shop = make_shop()
    client = owner_client(shop)
    _seed_cash_sale(client, amount="40")

    response = client.get("/api/journal/ledger", params={"format": "xlsx", "period": "month"})
    assert response.status_code == 200
    assert "spreadsheetml" in response.headers.get("content-type", "")
    disposition = response.headers.get("content-disposition", "")
    assert "attachment" in disposition
    assert "mayor" in disposition.lower()
    assert "agentia" not in disposition.lower()
    filename = disposition.split("filename=")[-1].strip().strip('"')
    assert filename.lower().endswith(".xlsx")
    assert " " not in filename

    book = load_workbook(BytesIO(response.content))
    sheet = book.active
    values = [[cell.value for cell in row] for row in sheet.iter_rows()]
    flat = " ".join(str(cell) for row in values for cell in row if cell is not None)

    assert "Authentic Closet" in flat or "Closet" in flat
    assert "Mayor" in flat
    assert "Dueño" in flat or "actor" in flat.lower() or "generado" in flat.lower()
    assert any("per" in str(cell).lower() for row in values for cell in row if cell)

    header_row = next(
        row
        for row in values
        if row and {str(c) for c in row if c is not None} >= set(MAYOR_COLUMNS)
    )
    header_text = [str(c) for c in header_row if c is not None]
    for col in MAYOR_COLUMNS:
        assert col in header_text

    assert "1100" in flat
    # Cash sale 40 → Caja debit 40 as Excel number somewhere.
    assert 40.0 in [cell for row in values for cell in row] or 40 in [
        cell for row in values for cell in row
    ]
    # Running / closing balance concept present.
    assert "saldo" in flat.lower()
    assert any(
        "cierre" in str(cell).lower() or "saldo" in str(cell).lower()
        for row in values
        for cell in row
        if cell is not None
    )


def test_mayor_xlsx_account_filter_matches_screen() -> None:
    shop = make_shop()
    client = owner_client(shop)
    _seed_cash_sale(client, amount="40")

    screen = client.get("/api/journal/ledger", params={"period": "month", "account": "4100"})
    assert screen.status_code == 200
    screen_accounts = screen.json()["accounts"]
    assert len(screen_accounts) == 1
    assert screen_accounts[0]["code"] == "4100"

    response = client.get(
        "/api/journal/ledger",
        params={"format": "xlsx", "period": "month", "account": "4100"},
    )
    assert response.status_code == 200
    book = load_workbook(BytesIO(response.content))
    sheet = book.active
    flat = " ".join(
        str(cell.value)
        for row in sheet.iter_rows()
        for cell in row
        if cell.value is not None
    )
    assert "4100" in flat
    # Filtered export should not dump unrelated asset cash account as a section title
    # beyond possible origin noise — closing/account header for 1100 must be absent.
    assert "1100" not in flat


def test_mayor_xlsx_empty_period_returns_notice_not_500() -> None:
    shop = make_shop()
    client = owner_client(shop)
    query = urlencode(
        {
            "format": "xlsx",
            "from": "2020-01-01T00:00:00+00:00",
            "to": "2020-01-02T00:00:00+00:00",
        }
    )
    response = client.get(f"/api/journal/ledger?{query}")
    assert response.status_code == 200
    book = load_workbook(BytesIO(response.content))
    sheet = book.active
    flat = " ".join(
        str(cell.value)
        for row in sheet.iter_rows()
        for cell in row
        if cell.value is not None
    )
    assert EMPTY_NOTICE in flat


def test_mayor_xlsx_shows_post_and_reverse() -> None:
    shop = make_shop()
    client = owner_client(shop)
    mid = _seed_cash_sale(client, amount="50")
    voided = client.post(f"/api/cash/{mid}/void", json={"reason": "duplicado"})
    assert voided.status_code == 200

    response = client.get("/api/journal/ledger", params={"format": "xlsx", "period": "month"})
    assert response.status_code == 200
    book = load_workbook(BytesIO(response.content))
    sheet = book.active
    flat = " ".join(
        str(cell.value)
        for row in sheet.iter_rows()
        for cell in row
        if cell.value is not None
    )
    assert "post" in flat
    assert "reverse" in flat
