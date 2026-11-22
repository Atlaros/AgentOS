"""T1 cash drawer session: open, close with arqueo, require open session to post."""

from __future__ import annotations

from decimal import Decimal

from tests.conftest import make_shop, owner_client


def test_cash_session_open_close_and_requires_open_to_post() -> None:
    shop = make_shop()
    client = owner_client(shop)

    empty = client.get("/api/cash/session")
    assert empty.status_code == 200
    assert empty.json()["session"] is None

    blocked = client.post(
        "/api/cash",
        json={"direction": "in", "amount": "10", "reason": "smoke"},
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"] == "session_required"

    opened = client.post("/api/cash/session/open", json={"opening_float": "200.00"})
    assert opened.status_code == 200
    body = opened.json()
    assert body["status"] == "open"
    assert body["opening_float"] == "200.00"
    assert body["expected_cash"] == "200.00"
    session_id = body["id"]

    again = client.post("/api/cash/session/open", json={"opening_float": "50"})
    assert again.status_code == 409
    assert again.json()["detail"] == "session_open"

    posted = client.post(
        "/api/cash",
        json={"direction": "in", "amount": "50", "reason": "venta mostrador"},
    )
    assert posted.status_code == 200

    out = client.post(
        "/api/cash",
        json={"direction": "out", "amount": "20", "reason": "envio"},
    )
    assert out.status_code == 200

    current = client.get("/api/cash/session").json()["session"]
    assert current["id"] == session_id
    assert current["status"] == "open"
    assert current["opening_float"] == "200.00"
    assert current["in"] == "50.00"
    assert current["out"] == "20.00"
    assert current["expected_cash"] == "230.00"

    book = client.get("/api/cash").json()
    assert book["session"]["id"] == session_id
    assert book["session"]["expected_cash"] == "230.00"
    assert book["balance"] == "30" or book["balance"] == "30.00"
    # session-scoped movements only in book when a session is open
    assert book["count"] == 2

    bad_close = client.post(
        "/api/cash/session/close",
        json={"counted_cash": "100.00", "note": ""},
    )
    assert bad_close.status_code == 400
    assert bad_close.json()["detail"] == "note_required"

    closed = client.post(
        "/api/cash/session/close",
        json={"counted_cash": "230.00", "note": ""},
    )
    assert closed.status_code == 200
    closed_body = closed.json()
    assert closed_body["status"] == "closed"
    assert closed_body["counted_cash"] == "230.00"
    assert closed_body["expected_cash"] == "230.00"
    assert closed_body["difference"] == "0.00"

    assert client.get("/api/cash/session").json()["session"] is None
    history = client.get("/api/cash/session/history").json()["closes"]
    assert len(history) >= 1
    assert history[0]["id"] == session_id
    assert history[0]["difference"] == "0.00"

    blocked_again = client.post(
        "/api/cash",
        json={"direction": "in", "amount": "5", "reason": "despues"},
    )
    assert blocked_again.status_code == 409
    assert blocked_again.json()["detail"] == "session_required"


def test_cash_session_close_with_difference_requires_note() -> None:
    shop = make_shop()
    client = owner_client(shop)
    client.post("/api/cash/session/open", json={"opening_float": "100"})
    client.post("/api/cash", json={"direction": "in", "amount": "10", "reason": "x"})
    closed = client.post(
        "/api/cash/session/close",
        json={"counted_cash": "90", "note": "faltante arqueo"},
    )
    assert closed.status_code == 200
    assert Decimal(closed.json()["difference"]) == Decimal("-20.00")
    assert closed.json()["close_note"] == "faltante arqueo"
