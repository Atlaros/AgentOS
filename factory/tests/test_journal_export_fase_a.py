"""T1 Contabilidad export Fase A: Diario xlsx + supervisor-only (ADR-011)."""

from __future__ import annotations

from io import BytesIO
from urllib.parse import urlencode

from fastapi.testclient import TestClient
from openpyxl import load_workbook

from tests.conftest import make_shop, owner_client

ES_COLUMNS = ("fecha", "asiento", "cuenta", "descripción", "debe", "haber", "origen")
EMPTY_NOTICE = "Sin movimientos en el período"


def _panel_client(shop, secret: str) -> TestClient:
    from factory_os.api.main import create_app
    from tests.conftest import api_settings

    client = TestClient(create_app(shop, api_settings()))
    client.headers["Authorization"] = f"Bearer {secret}"
    return client


def _seed_roles(owner: TestClient) -> None:
    staff = owner.post(
        "/api/panel/users",
        json={
            "name": "Luis Staff",
            "email": "luis-journal-export@taller.local",
            "role": "staff",
            "secret": "staff-journal-export",
        },
    )
    assert staff.status_code == 200
    supervisor = owner.post(
        "/api/panel/users",
        json={
            "name": "Ana Super",
            "email": "ana-journal-export@taller.local",
            "role": "supervisor",
            "secret": "super-journal-export",
        },
    )
    assert supervisor.status_code == 200


def _seed_cash_sale(client: TestClient, amount: str = "40") -> str:
    client.post("/api/cash/session/open", json={"opening_float": "0"})
    posted = client.post(
        "/api/cash",
        json={
            "direction": "in",
            "amount": amount,
            "reason": "venta mostrador",
            "category": "venta",
            "method": "cash",
        },
    )
    assert posted.status_code == 200
    return posted.json()["id"]


def test_staff_forbidden_on_contabilidad_exports_supervisor_and_owner_ok() -> None:
    shop = make_shop()
    owner = owner_client(shop)
    _seed_roles(owner)
    _seed_cash_sale(owner)

    staff = _panel_client(shop, "staff-journal-export")
    for path, params in (
        ("/api/journal/export", {"format": "csv", "period": "month"}),
        ("/api/journal/export", {"format": "xlsx", "period": "month"}),
        ("/api/ledger/export", {"format": "csv", "period": "month"}),
        ("/api/journal/trial-balance", {"format": "csv", "period": "month"}),
    ):
        denied = staff.get(path, params=params)
        assert denied.status_code == 403, f"{path} {params} → {denied.status_code}"

    # Screen trial-balance (no format) stays open to staff via require_human.
    assert staff.get("/api/journal/trial-balance", params={"period": "month"}).status_code == 200

    supervisor = _panel_client(shop, "super-journal-export")
    for path, params in (
        ("/api/journal/export", {"format": "csv", "period": "month"}),
        ("/api/journal/export", {"format": "xlsx", "period": "month"}),
        ("/api/ledger/export", {"format": "csv", "period": "month"}),
        ("/api/journal/trial-balance", {"format": "csv", "period": "month"}),
    ):
        ok = supervisor.get(path, params=params)
        assert ok.status_code == 200, f"supervisor {path} → {ok.status_code}"

    for path, params in (
        ("/api/journal/export", {"format": "xlsx", "period": "month"}),
        ("/api/ledger/export", {"format": "pdf", "period": "month"}),
        ("/api/journal/trial-balance", {"format": "csv", "period": "month"}),
    ):
        ok = owner.get(path, params=params)
        assert ok.status_code == 200, f"owner {path} → {ok.status_code}"


def test_diario_xlsx_spanish_columns_header_totals_and_slug_filename() -> None:
    shop = make_shop()
    client = owner_client(shop)
    _seed_cash_sale(client, amount="40")

    response = client.get("/api/journal/export", params={"format": "xlsx", "period": "month"})
    assert response.status_code == 200
    assert "spreadsheetml" in response.headers.get("content-type", "")
    disposition = response.headers.get("content-disposition", "")
    assert "attachment" in disposition
    assert ".xlsx" in disposition
    assert "agentia" not in disposition.lower()
    assert "diario" in disposition.lower() or "journal" not in disposition.lower()
    # Descriptive slug: shop/tenant based, not a bare generic name.
    assert "filename=" in disposition
    filename = disposition.split("filename=")[-1].strip().strip('"')
    assert " " not in filename
    assert filename.lower().endswith(".xlsx")
    assert filename.lower() != "journal_export.xlsx"

    book = load_workbook(BytesIO(response.content))
    sheet = book.active
    values = [[cell.value for cell in row] for row in sheet.iter_rows()]
    flat = " ".join(str(cell) for row in values for cell in row if cell is not None)

    assert "Authentic Closet" in flat or "Closet" in flat
    assert "Diario" in flat
    assert "Dueño" in flat or "actor" in flat.lower() or "generado" in flat.lower()
    assert any("per" in str(cell).lower() for row in values for cell in row if cell)

    # Column header row with Spanish concepts.
    header_row = next(
        row
        for row in values
        if row and {str(c) for c in row if c is not None} >= set(ES_COLUMNS)
    )
    header_text = [str(c) for c in header_row if c is not None]
    for col in ES_COLUMNS:
        assert col in header_text

    assert "1100" in flat
    assert "40" in flat or 40.0 in [cell for row in values for cell in row] or 40 in [
        cell for row in values for cell in row
    ]
    assert "debe" in flat.lower() and "haber" in flat.lower()
    # Totals row present.
    assert any(
        str(cell).lower().startswith("total") for row in values for cell in row if cell is not None
    )


def test_diario_xlsx_empty_period_returns_notice_not_500() -> None:
    shop = make_shop()
    client = owner_client(shop)
    query = urlencode(
        {
            "format": "xlsx",
            "from": "2020-01-01T00:00:00+00:00",
            "to": "2020-01-02T00:00:00+00:00",
        }
    )
    response = client.get(f"/api/journal/export?{query}")
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


def test_diario_xlsx_shows_post_and_reverse() -> None:
    shop = make_shop()
    client = owner_client(shop)
    mid = _seed_cash_sale(client, amount="50")
    voided = client.post(f"/api/cash/{mid}/void", json={"reason": "duplicado"})
    assert voided.status_code == 200

    response = client.get("/api/journal/export", params={"format": "xlsx", "period": "month"})
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


def test_diario_csv_uses_spanish_columns() -> None:
    shop = make_shop()
    client = owner_client(shop)
    _seed_cash_sale(client)

    response = client.get("/api/journal/export", params={"format": "csv", "period": "month"})
    assert response.status_code == 200
    text = response.text
    for col in ES_COLUMNS:
        assert col in text
    assert "1100" in text
    assert "cash" in text
