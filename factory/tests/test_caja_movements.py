"""T2 cash movements: actor, category, method, soft void (ADR-009)."""

from __future__ import annotations

from decimal import Decimal

from tests.conftest import make_shop, owner_client


def test_cash_movement_carries_actor_category_method_and_void() -> None:
    shop = make_shop()
    client = owner_client(shop)
    client.post("/api/cash/session/open", json={"opening_float": "100"})

    posted = client.post(
        "/api/cash",
        json={
            "direction": "out",
            "amount": "25",
            "reason": "envio pedido",
            "category": "envio",
            "method": "cash",
        },
    )
    assert posted.status_code == 200
    body = posted.json()
    assert body["category"] == "envio"
    assert body["method"] == "cash"
    assert body["status"] == "recorded"
    assert body["recorded_by_name"]
    assert body["created_at"]
    movement_id = body["id"]

    book = client.get("/api/cash").json()
    row = next(item for item in book["movements"] if item["id"] == movement_id)
    assert row["category"] == "envio"
    assert row["method"] == "cash"
    assert row["status"] == "recorded"
    assert row["recorded_by_name"]
    assert row["created_at"]
    assert book["session"]["out"] == "25.00"
    assert book["session"]["expected_cash"] == "75.00"

    bad_void = client.post(f"/api/cash/{movement_id}/void", json={"reason": ""})
    assert bad_void.status_code == 400
    assert bad_void.json()["detail"] == "void_reason_required"

    voided = client.post(
        f"/api/cash/{movement_id}/void",
        json={"reason": "cargo duplicado"},
    )
    assert voided.status_code == 200
    void_body = voided.json()
    assert void_body["status"] == "voided"
    assert void_body["void_reason"] == "cargo duplicado"
    assert void_body["voided_by_name"]
    assert void_body["voided_at"]

    after = client.get("/api/cash").json()
    void_row = next(item for item in after["movements"] if item["id"] == movement_id)
    assert void_row["status"] == "voided"
    assert void_row["void_reason"] == "cargo duplicado"
    # Voided rows stay visible but do not affect arqueo.
    assert after["count"] == 1
    assert after["session"]["out"] == "0.00"
    assert after["session"]["expected_cash"] == "100.00"
    assert after["balance"] == "0" or after["balance"] == "0.00"

    again = client.post(
        f"/api/cash/{movement_id}/void",
        json={"reason": "otra vez"},
    )
    assert again.status_code == 409
    assert again.json()["detail"] == "already_voided"


def test_cash_void_unknown_movement() -> None:
    shop = make_shop()
    client = owner_client(shop)
    client.post("/api/cash/session/open", json={"opening_float": "10"})
    missing = client.post(
        "/api/cash/00000000-0000-0000-0000-000000000099/void",
        json={"reason": "no existe"},
    )
    assert missing.status_code == 404
    assert missing.json()["detail"] == "movement_not_found"


def test_cash_out_without_reason_rejected_when_category_set() -> None:
    """Salidas siguen exigiendo motivo no vacío (ADR-009)."""
    shop = make_shop()
    client = owner_client(shop)
    client.post("/api/cash/session/open", json={"opening_float": "10"})
    bad = client.post(
        "/api/cash",
        json={"direction": "out", "amount": "5", "reason": "  ", "category": "gasto"},
    )
    assert bad.status_code == 400
    assert bad.json()["detail"] == "reason_required"
