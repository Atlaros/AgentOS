"""Per-tenant employee roster: catalog seed, enable/disable, clones (ADR-026)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from factory_os.domain.models import EmployeeRole, PILOT_TENANT_ID
from factory_os.domain.provision import provision_business
from factory_os.domain.tenant_employees import (
    LOCKED_BASE_ROLES,
    archive_employee,
    clone_employee,
    ensure_tenant_roster,
    list_employees,
    set_employee_enabled,
    set_employee_profile,
)


def test_provision_seeds_catalog_roster_without_orchestrator() -> None:
    tid = provision_business(name="Roster Cafe", industry="cafe")
    rows = list_employees(tid)
    keys = {row.employee_key for row in rows}
    assert "orchestrator" not in keys
    assert "sales" in keys
    assert "collections" in keys
    assert all(not row.is_clone for row in rows)
    assert all(row.enabled for row in rows)


def test_cannot_disable_sales_or_collections() -> None:
    tid = provision_business(name="Locked", industry="cafe")
    for role in LOCKED_BASE_ROLES:
        with pytest.raises(ValueError, match="employee_locked"):
            set_employee_enabled(tid, role.value, False)


def test_disable_ops_marks_row_disabled() -> None:
    tid = provision_business(name="Ops Off", industry="cafe")
    set_employee_enabled(tid, "ops", False)
    ops = next(row for row in list_employees(tid) if row.employee_key == "ops")
    assert ops.enabled is False


def test_rename_updates_display_name() -> None:
    tid = provision_business(name="Rename", industry="cafe")
    set_employee_profile(tid, "sales", display_name="Adri Café", style="cálida")
    sales = next(row for row in list_employees(tid) if row.employee_key == "sales")
    assert sales.display_name == "Adri Café"
    assert sales.style == "cálida"


def test_clone_inherits_base_role_only() -> None:
    tid = provision_business(name="Clone Shop", industry="cafe")
    clone = clone_employee(
        tid, base_role=EmployeeRole.SALES, display_name="Adri Promo", style="corta"
    )
    assert clone.is_clone is True
    assert clone.base_role is EmployeeRole.SALES
    assert clone.display_name == "Adri Promo"
    assert clone.enabled is True
    assert clone.employee_key != "sales"
    rows = list_employees(tid)
    assert any(row.employee_key == clone.employee_key for row in rows)


def test_archive_clone_hides_from_active_list() -> None:
    tid = provision_business(name="Archive", industry="cafe")
    clone = clone_employee(tid, base_role=EmployeeRole.OPS, display_name="Ops Extra")
    archive_employee(tid, clone.employee_key)
    active = list_employees(tid, include_archived=False)
    assert all(row.employee_key != clone.employee_key for row in active)
    all_rows = list_employees(tid, include_archived=True)
    archived = next(row for row in all_rows if row.employee_key == clone.employee_key)
    assert archived.archived is True
    assert archived.enabled is False


def test_ensure_roster_is_idempotent_for_pilot() -> None:
    ensure_tenant_roster(PILOT_TENANT_ID)
    first = list_employees(PILOT_TENANT_ID)
    ensure_tenant_roster(PILOT_TENANT_ID)
    second = list_employees(PILOT_TENANT_ID)
    assert {row.employee_key for row in first} == {row.employee_key for row in second}


def test_clone_rejects_unknown_base_and_empty_name() -> None:
    tid = provision_business(name="Bad Clone", industry="cafe")
    with pytest.raises(ValueError, match="display_name_required"):
        clone_employee(tid, base_role=EmployeeRole.SALES, display_name="  ")
