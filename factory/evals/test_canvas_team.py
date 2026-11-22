"""Evals: canvas team assignments never grant payment confirmation (ADR-027)."""

from uuid import uuid4

import pytest

from factory_os.domain.flow_canvas import clear_published_flow_maps, publish_flow_map
from factory_os.domain.tenant_employees import clear_tenant_employees, ensure_tenant_roster


def setup_function() -> None:
    clear_published_flow_maps()
    clear_tenant_employees()


def test_publishing_sales_on_whatsapp_does_not_open_payment_confirm() -> None:
    """Team placement is assignment only — confirm_payment floor stays never."""
    from factory_os.domain.autonomy import template_autonomy

    tenant = uuid4()
    ensure_tenant_roster(tenant)
    publish_flow_map(
        tenant,
        ["whatsapp", "pedido", "cobros"],
        team=[{"employee_key": "sales", "module": "whatsapp"}],
    )
    floor = {grant.action: grant.level for grant in template_autonomy("cafe")}
    assert floor["confirm_payment"] == "never"


def test_disabled_ops_cannot_publish_on_team() -> None:
    from factory_os.domain.tenant_employees import set_employee_enabled

    tenant = uuid4()
    ensure_tenant_roster(tenant)
    set_employee_enabled(tenant, "ops", False)
    with pytest.raises(ValueError, match="employee_disabled"):
        publish_flow_map(
            tenant,
            ["whatsapp", "pedido", "cobros"],
            team=[{"employee_key": "ops", "module": "pedido"}],
        )
