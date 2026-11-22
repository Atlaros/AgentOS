"""T6 cash filters + CSV/PDF export (ADR-009)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from tests.conftest import make_shop, owner_client


def _open_and_seed(client) -> tuple[str, str]:
    client.post("/api/cash/session/open", json={"opening_float": "100"})
    out = client.post(
        "/api/cash",
        json={
            "direction": "out",
            "amount": "15",
            "reason": "envio pedido",
            "category": "envio",
            "method": "cash",
        },
    )
    assert out.status_code == 200
    inn = client.post(
        "/api/cash",
        json={
            "direction": "in",
            "amount": "40",
            "reason": "venta mostrador",
            "category": "venta",
            "method": "cash",
        },
    )
    assert inn.status_code == 200
    return out.json()["id"], inn.json()["id"]


def test_cash_list_filters_by_direction_category_and_status() -> None:
    shop = make_shop()
    client = owner_client(shop)
    out_id, in_id = _open_and_seed(client)

    only_out = client.get("/api/cash", params={"direction": "out"})
    assert only_out.status_code == 200
    rows = only_out.json()["movements"]
    assert [row["id"] for row in rows] == [out_id]
    assert only_out.json()["count"] == 1

    only_venta = client.get("/api/cash", params={"category": "venta"})
    assert only_venta.status_code == 200
    assert [row["id"] for row in only_venta.json()["movements"]] == [in_id]

    client.post(f"/api/cash/{out_id}/void", json={"reason": "duplicado"})
    active = client.get("/api/cash", params={"status": "recorded"})
    assert active.status_code == 200
    assert [row["id"] for row in active.json()["movements"]] == [in_id]

    voided = client.get("/api/cash", params={"status": "voided"})
    assert voided.status_code == 200
    assert [row["id"] for row in voided.json()["movements"]] == [out_id]


def test_cash_export_csv_and_pdf() -> None:
    shop = make_shop()
    client = owner_client(shop)
    _open_and_seed(client)

    csv_res = client.get("/api/cash/export", params={"format": "csv", "direction": "in"})
    assert csv_res.status_code == 200
    assert "text/csv" in csv_res.headers.get("content-type", "")
    assert "attachment" in csv_res.headers.get("content-disposition", "")
    text = csv_res.text
    assert "direction" in text.splitlines()[0]
    assert "venta" in text
    assert "envio" not in text

    pdf_res = client.get("/api/cash/export", params={"format": "pdf"})
    assert pdf_res.status_code == 200
    assert "application/pdf" in pdf_res.headers.get("content-type", "")
    assert pdf_res.content[:4] == b"%PDF"

    bad = client.get("/api/cash/export", params={"format": "xlsx"})
    assert bad.status_code == 400
    assert bad.json()["detail"] == "bad_format"


def test_cash_filter_by_date_range() -> None:
    shop = make_shop()
    client = owner_client(shop)
    _open_and_seed(client)
    now = datetime.now(UTC)
    future = (now + timedelta(days=1)).date().isoformat()
    past = (now - timedelta(days=2)).date().isoformat()

    empty = client.get("/api/cash", params={"from": future})
    assert empty.status_code == 200
    assert empty.json()["movements"] == []

    spanned = client.get("/api/cash", params={"from": past, "to": future})
    assert spanned.status_code == 200
    assert spanned.json()["count"] == 2
