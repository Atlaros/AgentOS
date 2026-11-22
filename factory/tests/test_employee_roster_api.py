"""Operator/owner employee roster HTTP API (ADR-026)."""

from factory_os.domain.operator_registry import clear_operator_registry
from factory_os.domain.provision import provision_business
from factory_os.domain.tenant_employees import clear_tenant_employees
from tests.conftest import make_shop, owner_client


def _fresh_client():
    clear_operator_registry()
    clear_tenant_employees()
    tid = provision_business(name="Roster Cafe", industry="cafe")
    client = owner_client(make_shop())
    return client, tid


def test_operator_lists_seeded_catalog_employees() -> None:
    client, tid = _fresh_client()
    response = client.get(f"/api/operator/employees?tenant_id={tid}")
    assert response.status_code == 200
    rows = response.json()["employees"]
    keys = {row["employee_key"] for row in rows}
    assert "sales" in keys
    assert "collections" in keys
    sales = next(row for row in rows if row["employee_key"] == "sales")
    assert sales["enabled"] is True
    assert sales["locked"] is True
    assert sales["is_clone"] is False


def test_operator_can_rename_and_disable_non_locked() -> None:
    client, tid = _fresh_client()
    renamed = client.patch(
        "/api/operator/employees",
        json={
            "tenant_id": str(tid),
            "employee_key": "ops",
            "display_name": "Ops Norte",
            "style": "corto y claro",
        },
    )
    assert renamed.status_code == 200
    assert renamed.json()["employee"]["display_name"] == "Ops Norte"
    assert renamed.json()["employee"]["style"] == "corto y claro"

    disabled = client.patch(
        "/api/operator/employees",
        json={"tenant_id": str(tid), "employee_key": "ops", "enabled": False},
    )
    assert disabled.status_code == 200
    assert disabled.json()["employee"]["enabled"] is False

    locked = client.patch(
        "/api/operator/employees",
        json={"tenant_id": str(tid), "employee_key": "sales", "enabled": False},
    )
    assert locked.status_code == 400
    assert "employee_locked" in locked.json()["detail"]


def test_operator_can_clone_and_archive() -> None:
    client, tid = _fresh_client()
    created = client.post(
        "/api/operator/employees",
        json={
            "tenant_id": str(tid),
            "base_role": "sales",
            "display_name": "Adri Promo",
            "style": "promo",
        },
    )
    assert created.status_code == 200
    emp = created.json()["employee"]
    assert emp["is_clone"] is True
    assert emp["base_role"] == "sales"
    assert emp["display_name"] == "Adri Promo"

    archived = client.request(
        "DELETE",
        "/api/operator/employees",
        json={"tenant_id": str(tid), "employee_key": emp["employee_key"]},
    )
    assert archived.status_code == 200
    assert archived.json()["employee"]["archived"] is True
    assert archived.json()["employee"]["enabled"] is False

    listed = client.get(f"/api/operator/employees?tenant_id={tid}").json()["employees"]
    assert emp["employee_key"] not in {row["employee_key"] for row in listed}
