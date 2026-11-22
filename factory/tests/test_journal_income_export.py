"""T3 Contabilidad export Fase A: Resultado xlsx + PDF + supervisor-only (ADR-011)."""

from __future__ import annotations

from io import BytesIO
from urllib.parse import urlencode

from openpyxl import load_workbook

from tests.conftest import make_shop, owner_client
from tests.test_journal_export_fase_a import EMPTY_NOTICE, _panel_client, _seed_cash_sale, _seed_roles

INCOME_LABELS = (
    "Ingresos (Ventas)",
    "Costo de ventas",
    "Gastos",
    "Retiros",
    "Resultado gerencial",
)
MANAGERIAL_FOOTER = "Contabilidad gerencial. No sustituye estados financieros oficiales."


def test_staff_forbidden_on_income_export_json_view_ok() -> None:
    shop = make_shop()
    owner = owner_client(shop)
    _seed_roles(owner)
    _seed_cash_sale(owner)

    staff = _panel_client(shop, "staff-journal-export")
    for fmt in ("xlsx", "pdf"):
        denied = staff.get("/api/journal/income", params={"format": fmt, "period": "month"})
        assert denied.status_code == 403, f"staff format={fmt} → {denied.status_code}"

    assert staff.get("/api/journal/income", params={"period": "month"}).status_code == 200

    supervisor = _panel_client(shop, "super-journal-export")
    for fmt in ("xlsx", "pdf"):
        ok = supervisor.get("/api/journal/income", params={"format": fmt, "period": "month"})
        assert ok.status_code == 200, f"supervisor format={fmt} → {ok.status_code}"

    assert owner.get("/api/journal/income", params={"format": "xlsx", "period": "month"}).status_code == 200
    assert owner.get("/api/journal/income", params={"format": "pdf", "period": "month"}).status_code == 200


def test_income_xlsx_spanish_labels_header_numbers_and_slug() -> None:
    shop = make_shop()
    client = owner_client(shop)
    _seed_cash_sale(client, amount="40")

    screen = client.get("/api/journal/income", params={"period": "month"})
    assert screen.status_code == 200
    screen_body = screen.json()
    assert screen_body["revenue"] == "40"
    assert screen_body["result"] == "40"

    response = client.get("/api/journal/income", params={"format": "xlsx", "period": "month"})
    assert response.status_code == 200
    assert "spreadsheetml" in response.headers.get("content-type", "")
    disposition = response.headers.get("content-disposition", "")
    assert "attachment" in disposition
    assert "resultado" in disposition.lower()
    assert "agentia" not in disposition.lower()
    filename = disposition.split("filename=")[-1].strip().strip('"')
    assert filename.lower().endswith(".xlsx")
    assert " " not in filename

    book = load_workbook(BytesIO(response.content))
    sheet = book.active
    values = [[cell.value for cell in row] for row in sheet.iter_rows()]
    flat = " ".join(str(cell) for row in values for cell in row if cell is not None)

    assert "Authentic Closet" in flat or "Closet" in flat
    assert "Resultado" in flat
    assert "Dueño" in flat or "actor" in flat.lower() or "generado" in flat.lower()
    assert any("per" in str(cell).lower() for row in values for cell in row if cell)

    for label in INCOME_LABELS:
        assert label in flat

    # Excel numbers matching screen revenue/result.
    cells = [cell for row in values for cell in row]
    assert 40.0 in cells or 40 in cells


def test_income_pdf_header_and_managerial_footer() -> None:
    shop = make_shop()
    client = owner_client(shop)
    _seed_cash_sale(client, amount="40")

    response = client.get("/api/journal/income", params={"format": "pdf", "period": "month"})
    assert response.status_code == 200
    assert "pdf" in response.headers.get("content-type", "")
    disposition = response.headers.get("content-disposition", "")
    assert "resultado" in disposition.lower()
    assert disposition.lower().endswith('.pdf"') or ".pdf" in disposition.lower()

    text = response.content.decode("latin-1", errors="replace")
    assert "Resultado" in text or "resultado" in text.lower()
    assert "Periodo" in text or "Período" in text or "periodo" in text.lower()
    assert MANAGERIAL_FOOTER in text
    assert "40" in text


def test_income_xlsx_empty_period_returns_notice_not_500() -> None:
    shop = make_shop()
    client = owner_client(shop)
    query = urlencode(
        {
            "format": "xlsx",
            "from": "2020-01-01T00:00:00+00:00",
            "to": "2020-01-02T00:00:00+00:00",
        }
    )
    response = client.get(f"/api/journal/income?{query}")
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


def test_income_pdf_empty_period_returns_notice() -> None:
    shop = make_shop()
    client = owner_client(shop)
    query = urlencode(
        {
            "format": "pdf",
            "from": "2020-01-01T00:00:00+00:00",
            "to": "2020-01-02T00:00:00+00:00",
        }
    )
    response = client.get(f"/api/journal/income?{query}")
    assert response.status_code == 200
    text = response.content.decode("latin-1", errors="replace")
    assert EMPTY_NOTICE in text
    assert MANAGERIAL_FOOTER in text
