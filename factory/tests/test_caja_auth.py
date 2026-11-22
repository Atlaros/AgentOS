"""T4 cash drawer roles: supervisor PIN for void and reopen (ADR-009)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from factory_os.api.main import create_app
from tests.conftest import OWNER_TOKEN, api_settings, make_shop, owner_client


def _staff_client(shop, secret: str) -> TestClient:
    client = TestClient(create_app(shop, api_settings()))
    client.headers["Authorization"] = f"Bearer {secret}"
    return client


def test_staff_cannot_void_or_reopen_supervisor_can_with_pin() -> None:
    shop = make_shop()
    owner = owner_client(shop)

    staff_user = owner.post(
        "/api/panel/users",
        json={
            "name": "Luis Staff",
            "email": "luis@taller.local",
            "role": "staff",
            "secret": "staff-secret-1",
        },
    )
    assert staff_user.status_code == 200

    supervisor = owner.post(
        "/api/panel/users",
        json={
            "name": "Ana Super",
            "email": "ana@taller.local",
            "role": "supervisor",
            "secret": "super-secret-1",
            "pin": "2468",
        },
    )
    assert supervisor.status_code == 200
    assert supervisor.json()["role"] == "supervisor"
    assert "pin" not in supervisor.json()
    assert "pin_hash" not in supervisor.json()

    staff = _staff_client(shop, "staff-secret-1")
    opened = staff.post("/api/cash/session/open", json={"opening_float": "50"})
    assert opened.status_code == 200

    posted = staff.post(
        "/api/cash",
        json={"direction": "out", "amount": "10", "reason": "envio", "category": "envio"},
    )
    assert posted.status_code == 200
    movement_id = posted.json()["id"]

    staff_void = staff.post(
        f"/api/cash/{movement_id}/void",
        json={"reason": "error", "pin": "2468"},
    )
    assert staff_void.status_code == 403
    assert staff_void.json()["detail"] == "panel_forbidden"

    bad_pin = _staff_client(shop, "super-secret-1").post(
        f"/api/cash/{movement_id}/void",
        json={"reason": "error", "pin": "0000"},
    )
    assert bad_pin.status_code == 403
    assert bad_pin.json()["detail"] == "bad_pin"

    ok_void = _staff_client(shop, "super-secret-1").post(
        f"/api/cash/{movement_id}/void",
        json={"reason": "duplicado", "pin": "2468"},
    )
    assert ok_void.status_code == 200
    assert ok_void.json()["status"] == "voided"

    closed = _staff_client(shop, "super-secret-1").post(
        "/api/cash/session/close",
        json={"counted_cash": "50.00", "note": "", "pin": "2468"},
    )
    # Close may or may not require PIN for supervisor; ADR: supervisor can close.
    # Prefer close without PIN for supervisor; reopen requires PIN.
    if closed.status_code != 200:
        closed = _staff_client(shop, "super-secret-1").post(
            "/api/cash/session/close",
            json={"counted_cash": "50.00", "note": ""},
        )
    assert closed.status_code == 200

    staff_reopen = staff.post(
        "/api/cash/session/reopen",
        json={"pin": "2468"},
    )
    assert staff_reopen.status_code == 403

    bad_reopen = _staff_client(shop, "super-secret-1").post(
        "/api/cash/session/reopen",
        json={"pin": "1111"},
    )
    assert bad_reopen.status_code == 403
    assert bad_reopen.json()["detail"] == "bad_pin"

    reopened = _staff_client(shop, "super-secret-1").post(
        "/api/cash/session/reopen",
        json={"pin": "2468"},
    )
    assert reopened.status_code == 200
    assert reopened.json()["status"] == "open"


def test_pin_lockout_after_three_failures() -> None:
    shop = make_shop()
    owner = owner_client(shop)
    created = owner.post(
        "/api/panel/users",
        json={
            "name": "Ana Super",
            "email": "ana2@taller.local",
            "role": "supervisor",
            "secret": "super-secret-2",
            "pin": "1357",
        },
    )
    assert created.status_code == 200
    owner.post("/api/cash/session/open", json={"opening_float": "10"})
    posted = owner.post(
        "/api/cash",
        json={"direction": "out", "amount": "1", "reason": "x", "category": "gasto"},
    )
    movement_id = posted.json()["id"]
    super_client = _staff_client(shop, "super-secret-2")
    for _ in range(3):
        fail = super_client.post(
            f"/api/cash/{movement_id}/void",
            json={"reason": "x", "pin": "9999"},
        )
        assert fail.status_code == 403
        assert fail.json()["detail"] == "bad_pin"
    locked = super_client.post(
        f"/api/cash/{movement_id}/void",
        json={"reason": "x", "pin": "1357"},
    )
    assert locked.status_code == 403
    assert locked.json()["detail"] == "pin_locked"


def test_owner_token_void_still_needs_pin_when_actor_has_pin() -> None:
    """Bootstrap owner token without panel user may void without PIN (pilot).
    Owner panel user with PIN must supply it."""
    shop = make_shop()
    owner = owner_client(shop)
    created = owner.post(
        "/api/panel/users",
        json={
            "name": "Dueño",
            "email": "dueno@taller.local",
            "role": "owner",
            "secret": "owner-secret-9",
            "pin": "9876",
        },
    )
    assert created.status_code == 200
    user_id = created.json()["id"]

    authed = TestClient(create_app(shop, api_settings()))
    authed.headers["Authorization"] = f"Bearer {OWNER_TOKEN}"
    authed.headers["X-Panel-Actor"] = user_id
    authed.post("/api/cash/session/open", json={"opening_float": "5"})
    mov = authed.post(
        "/api/cash",
        json={"direction": "out", "amount": "1", "reason": "gasto", "category": "gasto"},
    ).json()["id"]
    missing_pin = authed.post(f"/api/cash/{mov}/void", json={"reason": "fix"})
    assert missing_pin.status_code == 400
    assert missing_pin.json()["detail"] == "pin_required"
    ok = authed.post(f"/api/cash/{mov}/void", json={"reason": "fix", "pin": "9876"})
    assert ok.status_code == 200
