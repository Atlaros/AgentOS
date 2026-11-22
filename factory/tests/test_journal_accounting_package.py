"""T11 Contabilidad Fase C: monthly accounting package multi-sheet xlsx (ADR-011)."""

from __future__ import annotations

from io import BytesIO

from openpyxl import load_workbook

from tests.conftest import make_shop, owner_client
from tests.test_journal_export_fase_a import EMPTY_NOTICE, _panel_client, _seed_cash_sale

PACKAGE_SHEETS = ("Diario", "Mayor", "Comprobación", "Resultado", "Balance", "Hechos")


def _seed_roles(owner) -> None:
    staff = owner.post(
        "/api/panel/users",
        json={
            "name": "Luis Staff",
            "email": "luis-accounting-package@taller.local",
            "role": "staff",
            "secret": "staff-accounting-package",
        },
    )
    assert staff.status_code == 200
    supervisor = owner.post(
        "/api/panel/users",
        json={
            "name": "Ana Super",
            "email": "ana-accounting-package@taller.local",
            "role": "supervisor",
            "secret": "super-accounting-package",
        },
    )
    assert supervisor.status_code == 200


def _sheet_flat(blob: bytes, title: str) -> str:
    book = load_workbook(BytesIO(blob))
    sheet = book[title]
    return " ".join(
        str(cell.value)
        for row in sheet.iter_rows()
        for cell in row
        if cell.value is not None
    )


def test_staff_forbidden_on_accounting_package_supervisor_ok() -> None:
    shop = make_shop()
    owner = owner_client(shop)
    _seed_roles(owner)
    _seed_cash_sale(owner)

    staff = _panel_client(shop, "staff-accounting-package")
    denied = staff.get("/api/reports/accounting-package", params={"period": "month", "format": "xlsx"})
    assert denied.status_code == 403

    supervisor = _panel_client(shop, "super-accounting-package")
    ok = supervisor.get(
        "/api/reports/accounting-package",
        params={"period": "month", "format": "xlsx"},
    )
    assert ok.status_code == 200
    assert "spreadsheetml" in ok.headers.get("content-type", "")

    owner_ok = owner.get(
        "/api/reports/accounting-package",
        params={"period": "month", "format": "xlsx"},
    )
    assert owner_ok.status_code == 200


def test_accounting_package_xlsx_sheets_header_slug_and_download_log() -> None:
    shop = make_shop()
    client = owner_client(shop)
    _seed_cash_sale(client, amount="40")

    bad = client.get("/api/reports/accounting-package", params={"month": "2026-13"})
    assert bad.status_code == 400

    response = client.get(
        "/api/reports/accounting-package",
        params={"period": "month", "format": "xlsx"},
    )
    assert response.status_code == 200
    assert "spreadsheetml" in response.headers.get("content-type", "")

    disposition = response.headers.get("content-disposition", "")
    assert "attachment" in disposition
    assert ".xlsx" in disposition
    assert "agentia" not in disposition.lower()
    assert "paquete" in disposition.lower() and "contable" in disposition.lower()
    filename = disposition.split("filename=")[-1].strip().strip('"')
    assert " " not in filename
    assert filename.lower().endswith(".xlsx")

    book = load_workbook(BytesIO(response.content))
    assert tuple(book.sheetnames) == PACKAGE_SHEETS

    diario = _sheet_flat(response.content, "Diario")
    assert "Authentic Closet" in diario or "Closet" in diario
    assert "Diario" in diario
    assert "Dueño" in diario or "actor" in diario.lower() or "generado" in diario.lower()
    assert "1100" in diario
    assert "40" in diario or 40.0 in [
        cell.value for row in book["Diario"].iter_rows() for cell in row
    ]

    mayor = _sheet_flat(response.content, "Mayor")
    assert "Mayor" in mayor
    assert "1100" in mayor or "4100" in mayor

    hechos = _sheet_flat(response.content, "Hechos")
    assert "Hechos" in hechos or "cash" in hechos.lower() or "amount" in hechos.lower()

    for title in ("Comprobación", "Resultado", "Balance"):
        flat = _sheet_flat(response.content, title)
        assert flat  # header / content present

    logged = client.get("/api/reports/downloads/history").json()["downloads"][0]
    assert logged["report_id"] == "accounting_package"
    assert logged["format"] == "xlsx"
    assert logged["actor_name"] == "Dueño"
    assert logged["period_id"]  # YYYY-MM or month label


def test_accounting_package_empty_month_still_valid_xlsx_with_notices() -> None:
    shop = make_shop()
    client = owner_client(shop)

    response = client.get(
        "/api/reports/accounting-package",
        params={"month": "2020-01", "format": "xlsx"},
    )
    assert response.status_code == 200
    book = load_workbook(BytesIO(response.content))
    assert tuple(book.sheetnames) == PACKAGE_SHEETS

    for title in PACKAGE_SHEETS:
        flat = _sheet_flat(response.content, title)
        assert EMPTY_NOTICE in flat or "sin" in flat.lower() or flat

    logged = client.get("/api/reports/downloads/history").json()["downloads"][0]
    assert logged["report_id"] == "accounting_package"
    assert logged["period_id"] == "2020-01"
