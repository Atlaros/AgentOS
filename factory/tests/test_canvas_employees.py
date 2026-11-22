"""ADR-027: roster employees on the business canvas (equipo port)."""

from uuid import uuid4

import pytest

from factory_os.domain.flow_canvas import (
    clear_published_flow_maps,
    connect_employee_to_module,
    employee_node_id,
    get_published_team,
    place_employee,
    publish_flow_map,
    try_flow_map,
)
from factory_os.domain.models import EmployeeRole
from factory_os.domain.tenant_employees import (
    clear_tenant_employees,
    clone_employee,
    ensure_tenant_roster,
    list_employees,
    set_employee_enabled,
)


def setup_function() -> None:
    clear_published_flow_maps()
    clear_tenant_employees()


def test_place_employee_makes_emp_node() -> None:
    node, pos = place_employee(
        "sales",
        display_name="Adri",
        base_role=EmployeeRole.SALES,
        present=(),
    )
    assert node.id == "emp:sales"
    assert node.family == "employee"
    assert node.employee_key == "sales"
    assert node.kind == "employee"
    assert node.locked is False
    assert pos["x"] >= 8


def test_sales_can_connect_to_whatsapp_not_contabilidad() -> None:
    edge = connect_employee_to_module("emp:sales", "whatsapp", base_role=EmployeeRole.SALES)
    assert edge.source == "emp:sales"
    assert edge.target == "whatsapp"
    assert edge.port == "equipo"
    assert edge.locked is False
    with pytest.raises(ValueError, match="role_module_forbidden"):
        connect_employee_to_module("emp:sales", "contabilidad", base_role=EmployeeRole.SALES)


def test_disabled_employee_rejected_on_publish_team() -> None:
    tenant = uuid4()
    ensure_tenant_roster(tenant)
    set_employee_enabled(tenant, "ops", False)
    with pytest.raises(ValueError, match="employee_disabled"):
        publish_flow_map(
            tenant,
            ["whatsapp", "pedido", "cobros"],
            team=[{"employee_key": "ops", "module": "pedido"}],
        )


def test_publish_team_persists_assignments() -> None:
    tenant = uuid4()
    ensure_tenant_roster(tenant)
    kinds = publish_flow_map(
        tenant,
        ["whatsapp", "mostrador", "pedido", "cobros"],
        team=[
            {"employee_key": "sales", "module": "whatsapp"},
            {"employee_key": "collections", "module": "cobros"},
        ],
    )
    assert "pedido" in kinds
    team = get_published_team(tenant)
    assert ("sales", "whatsapp") in {(row.employee_key, row.module) for row in team}
    assert ("collections", "cobros") in {(row.employee_key, row.module) for row in team}


def test_try_flow_map_ignores_employee_ids() -> None:
    kinds = try_flow_map(["whatsapp", "pedido", "cobros", "emp:sales"])
    assert "emp:sales" not in kinds
    assert "pedido" in kinds


def test_clone_can_be_placed_and_assigned() -> None:
    tenant = uuid4()
    ensure_tenant_roster(tenant)
    clone = clone_employee(
        tenant,
        base_role=EmployeeRole.SALES,
        display_name="Adri mañana",
        style="cálida",
    )
    node, _ = place_employee(
        clone.employee_key,
        display_name=clone.display_name,
        base_role=clone.base_role,
        present=(),
    )
    assert node.id == employee_node_id(clone.employee_key)
    edge = connect_employee_to_module(
        node.id, "mostrador", base_role=EmployeeRole.SALES
    )
    assert edge.target == "mostrador"
    publish_flow_map(
        tenant,
        ["whatsapp", "pedido", "cobros", "mostrador"],
        team=[{"employee_key": clone.employee_key, "module": "mostrador"}],
    )
    team = get_published_team(tenant)
    assert any(row.employee_key == clone.employee_key for row in team)


def test_unknown_employee_key_not_in_roster_rejected() -> None:
    tenant = uuid4()
    ensure_tenant_roster(tenant)
    keys = {row.employee_key for row in list_employees(tenant)}
    assert "ghost" not in keys
    with pytest.raises(ValueError, match="employee_not_in_roster"):
        publish_flow_map(
            tenant,
            ["pedido", "cobros", "whatsapp"],
            team=[{"employee_key": "ghost", "module": "whatsapp"}],
        )
