"""ADR-015 Fase E slice 1: order / purchase-order attachments (E1–E3)."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

from factory_os.domain.models import OrderItem, PILOT_TENANT_ID, PaymentStatus
from tests.conftest import make_shop, owner_client

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
SKU = "h001-M-VP"


def _pending_order(shop):
    customer = shop.store.get_or_create_customer(PILOT_TENANT_ID, "59180005555")
    order = shop.store.create_order(
        PILOT_TENANT_ID,
        customer.id,
        OrderItem(SKU, "H001", 1, Decimal("1"), "BOB"),
    )
    payment = shop.store.create_payment(
        PILOT_TENANT_ID,
        order.id,
        "fake",
        "bn-entity-media",
        Decimal("1"),
        "BOB",
        "QR:entity-media",
        customer_id=customer.id,
    )
    assert payment.status is PaymentStatus.PENDING
    return order, payment


def _draft_purchase_order(shop):
    supplier = shop.store.create_supplier(PILOT_TENANT_ID, name="Adjuntos Sur")
    return shop.store.create_purchase_order(
        PILOT_TENANT_ID,
        supplier.id,
        [{"variant_sku": SKU, "quantity": 1, "unit_cost": "10"}],
        notes="oc adjuntos",
    )


def test_upload_png_to_order_and_list(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path))
    shop = make_shop()
    order, _payment = _pending_order(shop)
    client = owner_client(shop)

    posted = client.post(
        f"/api/orders/{order.id}/attachments",
        files={"file": ("ticket.png", PNG, "image/png")},
        data={"note": "foto del ticket"},
    )
    assert posted.status_code == 200, posted.text
    body = posted.json()
    assert "attachments" in body
    assert len(body["attachments"]) == 1
    row = body["attachments"][0]
    assert row["filename"] == "ticket.png"
    assert row["kind"] == "image"
    assert row["mime"] == "image/png"
    assert row["size_bytes"] == len(PNG)
    assert row["note"] == "foto del ticket"
    assert row["asset_id"]
    assert row["url"].startswith("/api/media/")
    assert row.get("thumb_url", "").startswith("/api/media/")

    listed = client.get(f"/api/orders/{order.id}/attachments")
    assert listed.status_code == 200
    assert len(listed.json()["attachments"]) == 1
    assert listed.json()["attachments"][0]["id"] == row["id"]

    asset_get = client.get(row["url"])
    assert asset_get.status_code == 200
    assert asset_get.content == PNG


def test_upload_png_to_purchase_order_and_list(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path))
    shop = make_shop()
    po = _draft_purchase_order(shop)
    client = owner_client(shop)

    posted = client.post(
        f"/api/purchase-orders/{po.id}/attachments",
        files={"file": ("factura.png", PNG, "image/png")},
    )
    assert posted.status_code == 200, posted.text
    rows = posted.json()["attachments"]
    assert len(rows) == 1
    assert rows[0]["filename"] == "factura.png"
    assert rows[0]["kind"] == "image"

    listed = client.get(f"/api/purchase-orders/{po.id}/attachments")
    assert listed.status_code == 200
    assert len(listed.json()["attachments"]) == 1


def test_attachments_require_auth(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path))
    shop = make_shop()
    order, _ = _pending_order(shop)
    po = _draft_purchase_order(shop)
    from factory_os.api.main import create_app
    from fastapi.testclient import TestClient

    bare = TestClient(create_app(shop=shop))
    assert bare.get(f"/api/orders/{order.id}/attachments").status_code == 401
    assert bare.post(
        f"/api/orders/{order.id}/attachments",
        files={"file": ("x.png", PNG, "image/png")},
    ).status_code == 401
    assert bare.get(f"/api/purchase-orders/{po.id}/attachments").status_code == 401


def test_unknown_entity_returns_404(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path))
    shop = make_shop()
    client = owner_client(shop)
    missing = uuid4()
    assert client.get(f"/api/orders/{missing}/attachments").status_code == 404
    assert (
        client.post(
            f"/api/orders/{missing}/attachments",
            files={"file": ("x.png", PNG, "image/png")},
        ).status_code
        == 404
    )
    assert client.get(f"/api/purchase-orders/{missing}/attachments").status_code == 404
    assert (
        client.post(
            f"/api/purchase-orders/{missing}/attachments",
            files={"file": ("x.png", PNG, "image/png")},
        ).status_code
        == 404
    )


def test_pdf_attachment_ok(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path))
    shop = make_shop()
    order, _ = _pending_order(shop)
    client = owner_client(shop)
    posted = client.post(
        f"/api/orders/{order.id}/attachments",
        files={"file": ("guia.pdf", PDF, "application/pdf")},
    )
    assert posted.status_code == 200, posted.text
    row = posted.json()["attachments"][0]
    assert row["kind"] == "document"
    assert row["mime"] == "application/pdf"
    assert row["url"].startswith("/api/media/")


def test_bad_type_rejected(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path))
    shop = make_shop()
    order, _ = _pending_order(shop)
    client = owner_client(shop)
    denied = client.post(
        f"/api/orders/{order.id}/attachments",
        files={"file": ("notes.txt", b"hello plain text", "text/plain")},
    )
    assert denied.status_code == 400
    assert denied.json()["detail"] == "bad_type"


def test_attach_does_not_confirm_payment(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path))
    shop = make_shop()
    order, payment = _pending_order(shop)
    client = owner_client(shop)
    posted = client.post(
        f"/api/orders/{order.id}/attachments",
        files={"file": ("comprobante.png", PNG, "image/png")},
        data={"note": "parece un comprobante"},
    )
    assert posted.status_code == 200, posted.text
    still = shop.store.get_payment(PILOT_TENANT_ID, payment.id)
    assert still is not None
    assert still.status is PaymentStatus.PENDING
    refreshed = shop.store.get_order(PILOT_TENANT_ID, order.id)
    assert refreshed is not None
    assert refreshed.status == order.status
