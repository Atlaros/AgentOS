"""T8 Contabilidad export Fase B: Conciliación (bank recon) xlsx + supervisor-only."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from io import BytesIO
from urllib.parse import urlencode
from uuid import uuid4

from openpyxl import load_workbook

from factory_os.domain.models import Payment, PaymentStatus
from tests.conftest import make_shop, owner_client
from tests.test_journal_export_fase_a import EMPTY_NOTICE, _panel_client, _seed_roles

BANCO_COLUMNS = ("fecha", "sentido", "monto", "memo", "match")
PAGO_COLUMNS = ("fecha", "proveedor", "monto", "match")


def _seed_qr_payment(shop, client, amount: str = "80") -> None:
    """Confirmed non-cash payment that posts Banco (1200) and appears in bank-recon."""
    now = datetime.now(UTC)
    payment = Payment(
        id=uuid4(),
        tenant_id=shop.store.tenant_id,
        order_id=None,
        provider="fake",
        provider_ref=f"pay-{uuid4().hex[:8]}",
        amount=Decimal(amount),
        currency="BOB",
        status=PaymentStatus.PENDING,
        qr_payload="QR:test",
        created_at=now,
    )
    shop.store.payments[payment.id] = payment
    shop.store.payments_by_ref[payment.provider_ref] = payment
    shop.store.confirm_from_adapter(payment.provider_ref)


def test_staff_forbidden_on_bank_recon_xlsx_json_view_ok() -> None:
    shop = make_shop()
    owner = owner_client(shop)
    _seed_roles(owner)
    _seed_qr_payment(shop, owner)

    staff = _panel_client(shop, "staff-journal-export")
    denied = staff.get("/api/journal/bank-recon", params={"format": "xlsx", "period": "month"})
    assert denied.status_code == 403

    assert staff.get("/api/journal/bank-recon", params={"period": "month"}).status_code == 200

    supervisor = _panel_client(shop, "super-journal-export")
    ok = supervisor.get("/api/journal/bank-recon", params={"format": "xlsx", "period": "month"})
    assert ok.status_code == 200

    assert owner.get("/api/journal/bank-recon", params={"format": "xlsx", "period": "month"}).status_code == 200


def test_bank_recon_xlsx_spanish_sections_header_numbers_and_slug() -> None:
    shop = make_shop()
    client = owner_client(shop)
    _seed_qr_payment(shop, client, amount="80")

    screen = client.get("/api/journal/bank-recon", params={"period": "month"})
    assert screen.status_code == 200
    screen_body = screen.json()
    assert len(screen_body["bank_lines"]) >= 1
    assert len(screen_body["payments"]) >= 1
    assert len(screen_body["matches"]) >= 1

    response = client.get("/api/journal/bank-recon", params={"format": "xlsx", "period": "month"})
    assert response.status_code == 200
    assert "spreadsheetml" in response.headers.get("content-type", "")
    disposition = response.headers.get("content-disposition", "")
    assert "attachment" in disposition
    assert "conciliacion" in disposition.lower()
    assert "agentia" not in disposition.lower()
    filename = disposition.split("filename=")[-1].strip().strip('"')
    assert filename.lower().endswith(".xlsx")
    assert " " not in filename

    book = load_workbook(BytesIO(response.content))
    sheet_names = [name.casefold() for name in book.sheetnames]
    assert any("banco" in name for name in sheet_names)
    assert any("pago" in name for name in sheet_names)

    flat_parts: list[str] = []
    cells: list[object] = []
    for sheet in book.worksheets:
        for row in sheet.iter_rows():
            for cell in row:
                if cell.value is not None:
                    flat_parts.append(str(cell.value))
                    cells.append(cell.value)
    flat = " ".join(flat_parts)

    assert "Authentic Closet" in flat or "Closet" in flat
    assert "Conciliación" in flat or "Conciliacion" in flat
    assert any("per" in part.lower() for part in flat_parts)
    assert "Dueño" in flat or "actor" in flat.lower() or "generado" in flat.lower()

    banco = next(sheet for sheet in book.worksheets if "banco" in sheet.title.casefold())
    banco_values = [[cell.value for cell in row] for row in banco.iter_rows()]
    header_row = next(
        row
        for row in banco_values
        if row and {str(c).casefold() for c in row if c is not None} >= set(BANCO_COLUMNS)
    )
    header_text = [str(c).casefold() for c in header_row if c is not None]
    for col in BANCO_COLUMNS:
        assert col in header_text

    pagos = next(sheet for sheet in book.worksheets if "pago" in sheet.title.casefold())
    pago_values = [[cell.value for cell in row] for row in pagos.iter_rows()]
    pago_header = next(
        row
        for row in pago_values
        if row and {str(c).casefold() for c in row if c is not None} >= set(PAGO_COLUMNS)
    )
    pago_header_text = [str(c).casefold() for c in pago_header if c is not None]
    for col in PAGO_COLUMNS:
        assert col in pago_header_text

    assert 80.0 in cells or 80 in cells
    assert "Sí" in flat or "Si" in flat or "sí" in flat.lower()


def test_bank_recon_xlsx_empty_period_returns_notice_not_500() -> None:
    shop = make_shop()
    client = owner_client(shop)
    query = urlencode(
        {
            "format": "xlsx",
            "from": "2020-01-01T00:00:00+00:00",
            "to": "2020-01-02T00:00:00+00:00",
        }
    )
    response = client.get(f"/api/journal/bank-recon?{query}")
    assert response.status_code == 200
    book = load_workbook(BytesIO(response.content))
    flat = " ".join(
        str(cell.value)
        for sheet in book.worksheets
        for row in sheet.iter_rows()
        for cell in row
        if cell.value is not None
    )
    assert EMPTY_NOTICE in flat


def test_bank_recon_xlsx_matches_screen_rows() -> None:
    shop = make_shop()
    client = owner_client(shop)
    _seed_qr_payment(shop, client, amount="80")

    screen = client.get("/api/journal/bank-recon", params={"period": "month"})
    assert screen.status_code == 200
    body = screen.json()
    assert body["bank_lines"]
    assert body["payments"]
    bank_memo = body["bank_lines"][0].get("memo") or ""
    provider = body["payments"][0].get("provider") or ""

    response = client.get("/api/journal/bank-recon", params={"format": "xlsx", "period": "month"})
    assert response.status_code == 200
    book = load_workbook(BytesIO(response.content))
    flat = " ".join(
        str(cell.value)
        for sheet in book.worksheets
        for row in sheet.iter_rows()
        for cell in row
        if cell.value is not None
    )
    if bank_memo:
        assert bank_memo in flat
    if provider:
        assert provider in flat
    for match in body["matches"]:
        assert str(match["entry_id"]) in flat or str(match["payment_id"]) in flat
