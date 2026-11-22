"""T7 Contabilidad export Fase B: Comprobación (trial balance) xlsx + supervisor-only."""

from __future__ import annotations

from io import BytesIO
from urllib.parse import urlencode

from openpyxl import load_workbook

from tests.conftest import make_shop, owner_client
from tests.test_journal_export_fase_a import EMPTY_NOTICE, _panel_client, _seed_cash_sale, _seed_roles

ES_COLUMNS = ("código", "cuenta", "debe", "haber")


def test_staff_forbidden_on_trial_xlsx_json_view_ok() -> None:
    shop = make_shop()
    owner = owner_client(shop)
    _seed_roles(owner)
    _seed_cash_sale(owner)

    staff = _panel_client(shop, "staff-journal-export")
    denied = staff.get("/api/journal/trial-balance", params={"format": "xlsx", "period": "month"})
    assert denied.status_code == 403

    # CSV export already supervisor-only (T1); JSON screen stays human.
    assert staff.get("/api/journal/trial-balance", params={"format": "csv", "period": "month"}).status_code == 403
    assert staff.get("/api/journal/trial-balance", params={"period": "month"}).status_code == 200

    supervisor = _panel_client(shop, "super-journal-export")
    ok = supervisor.get("/api/journal/trial-balance", params={"format": "xlsx", "period": "month"})
    assert ok.status_code == 200

    assert owner.get("/api/journal/trial-balance", params={"format": "xlsx", "period": "month"}).status_code == 200


def test_trial_xlsx_spanish_columns_header_totals_cuadra_and_slug() -> None:
    shop = make_shop()
    client = owner_client(shop)
    _seed_cash_sale(client, amount="40")

    screen = client.get("/api/journal/trial-balance", params={"period": "month"})
    assert screen.status_code == 200
    screen_body = screen.json()
    assert screen_body["balanced"] is True
    assert screen_body["total_debit"] == screen_body["total_credit"]
    assert float(screen_body["total_debit"]) == 40.0

    response = client.get("/api/journal/trial-balance", params={"format": "xlsx", "period": "month"})
    assert response.status_code == 200
    assert "spreadsheetml" in response.headers.get("content-type", "")
    disposition = response.headers.get("content-disposition", "")
    assert "attachment" in disposition
    assert "comprobacion" in disposition.lower()
    assert "agentia" not in disposition.lower()
    filename = disposition.split("filename=")[-1].strip().strip('"')
    assert filename.lower().endswith(".xlsx")
    assert " " not in filename

    book = load_workbook(BytesIO(response.content))
    sheet = book.active
    values = [[cell.value for cell in row] for row in sheet.iter_rows()]
    flat = " ".join(str(cell) for row in values for cell in row if cell is not None)

    assert "Authentic Closet" in flat or "Closet" in flat
    assert "Comprobación" in flat or "Comprobacion" in flat
    assert "Dueño" in flat or "actor" in flat.lower() or "generado" in flat.lower()
    assert any("per" in str(cell).lower() for row in values for cell in row if cell)

    header_row = next(
        row
        for row in values
        if row and {str(c) for c in row if c is not None} >= set(ES_COLUMNS)
    )
    header_text = [str(c) for c in header_row if c is not None]
    for col in ES_COLUMNS:
        assert col in header_text

    cells = [cell for row in values for cell in row]
    assert 40.0 in cells or 40 in cells
    assert any(str(cell).lower().startswith("total") for row in values for cell in row if cell is not None)
    assert "Cuadra" in flat or "cuadra" in flat.lower()
    assert any(
        str(cell) in {"Sí", "Si", "sí", "si", True} or str(cell).lower() == "sí"
        for row in values
        for cell in row
        if cell is not None
    ) or "Sí" in flat or "Si" in flat


def test_trial_xlsx_empty_period_returns_notice_not_500() -> None:
    shop = make_shop()
    client = owner_client(shop)
    query = urlencode(
        {
            "format": "xlsx",
            "from": "2020-01-01T00:00:00+00:00",
            "to": "2020-01-02T00:00:00+00:00",
        }
    )
    response = client.get(f"/api/journal/trial-balance?{query}")
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


def test_trial_xlsx_matches_screen_account_rows() -> None:
    shop = make_shop()
    client = owner_client(shop)
    _seed_cash_sale(client, amount="40")

    screen = client.get("/api/journal/trial-balance", params={"period": "month"})
    assert screen.status_code == 200
    codes = {row["code"] for row in screen.json()["rows"]}
    assert "1100" in codes

    response = client.get("/api/journal/trial-balance", params={"format": "xlsx", "period": "month"})
    assert response.status_code == 200
    book = load_workbook(BytesIO(response.content))
    sheet = book.active
    flat = " ".join(
        str(cell.value)
        for row in sheet.iter_rows()
        for cell in row
        if cell.value is not None
    )
    for code in codes:
        assert code in flat
