"""Autonomy floor governs tool execution."""

from factory_os.contracts.employees import EmployeeRole, identity_for
from factory_os.domain.autonomy import AutonomyDenied, template_autonomy, tighten_autonomy
from factory_os.domain.models import PILOT_TENANT_ID
from factory_os.harness.tools import ConfirmationRequired, ToolRuntime, ToolSpec


def _runtime(name: str, permission: str, *, confirm: bool = False) -> tuple[ToolRuntime, list[object]]:
    seen: list[object] = []

    def handler(identity, payload):  # noqa: ANN001
        seen.append(payload)
        return {"ok": True}

    return ToolRuntime([ToolSpec(name, permission, False, handler, confirmation_required=confirm)]), seen


def test_hand_made_payment_confirm_is_denied() -> None:
    runtime, seen = _runtime("payment.confirm", "payment.create_qr")
    cobros = identity_for(EmployeeRole.COBROS, PILOT_TENANT_ID)
    try:
        runtime.execute(cobros, "payment.confirm", {}, confirmed=True)
    except AutonomyDenied:
        assert seen == []
        return
    raise AssertionError("payment confirm ran")


def test_never_stock_floor_blocks_a_confirmed_adjust() -> None:
    runtime, seen = _runtime("inventory.adjust", "inventory.adjust", confirm=True)
    inventory = identity_for(EmployeeRole.INVENTORY, PILOT_TENANT_ID)
    grants = tighten_autonomy(template_autonomy("cafe"), action="adjust_stock", level="never")
    try:
        runtime.execute(
            inventory,
            "inventory.adjust",
            {"variant_sku": "c001", "quantity": 1},
            confirmed=True,
            autonomy=grants,
        )
    except AutonomyDenied as exc:
        assert exc.action == "adjust_stock"
        assert seen == []
        return
    raise AssertionError("stock adjust ran")


def test_template_floor_still_requires_confirmation_to_adjust_stock() -> None:
    runtime, seen = _runtime("inventory.adjust", "inventory.adjust", confirm=True)
    inventory = identity_for(EmployeeRole.INVENTORY, PILOT_TENANT_ID)
    try:
        runtime.execute(inventory, "inventory.adjust", {"variant_sku": "c001", "quantity": 1})
    except ConfirmationRequired:
        assert seen == []
        return
    raise AssertionError("stock adjust ran without confirmation")


def test_tenant_autonomy_tightening_is_used_by_the_runtime() -> None:
    from uuid import uuid4

    from factory_os.domain.autonomy import (
        clear_tenant_autonomy,
        grants_for_tenant,
        set_tenant_autonomy,
    )

    clear_tenant_autonomy()
    tenant = uuid4()
    set_tenant_autonomy(tenant, industry="cafe", action="adjust_stock", level="never")
    grants = grants_for_tenant(tenant, industry="cafe")
    stock = next(item for item in grants if item.action == "adjust_stock")
    assert stock.level == "never"
    runtime, seen = _runtime("inventory.adjust", "inventory.adjust", confirm=True)
    inventory = identity_for(EmployeeRole.INVENTORY, tenant)
    runtime.autonomy_for = lambda tid: grants_for_tenant(tid, industry="cafe")
    try:
        runtime.execute(
            inventory,
            "inventory.adjust",
            {"variant_sku": "c001", "quantity": 1},
            confirmed=True,
        )
    except AutonomyDenied as exc:
        assert exc.action == "adjust_stock"
        assert seen == []
        return
    raise AssertionError("stock adjust ran")


def test_tenant_autonomy_survives_a_memory_reset_on_postgres() -> None:
    import os
    from uuid import uuid4

    import pytest

    from factory_os.domain.autonomy import (
        clear_tenant_autonomy,
        grants_for_tenant,
        set_tenant_autonomy,
    )
    from factory_os.domain.postgres import apply_migrations
    from factory_os.domain.provision import provision_business

    url = os.environ.get("FACTORY_OS_TEST_DATABASE_URL")
    if not url:
        pytest.skip("FACTORY_OS_TEST_DATABASE_URL not set")
    clear_tenant_autonomy()
    tenant_id = uuid4()
    try:
        apply_migrations(url)
        provision_business(name="Autonomy Luna", industry="cafe", url=url, tenant_id=tenant_id)
        set_tenant_autonomy(
            tenant_id,
            industry="cafe",
            action="reply_customer",
            level="recommend",
            url=url,
        )
    except Exception as exc:
        pytest.skip(f"postgres not reachable: {exc}")
    clear_tenant_autonomy()
    reply = next(
        item
        for item in grants_for_tenant(tenant_id, industry="cafe", url=url)
        if item.action == "reply_customer"
    )
    assert reply.level == "recommend"


def test_missing_autonomy_table_keeps_overrides_in_memory(monkeypatch) -> None:
    import psycopg
    from uuid import uuid4

    from factory_os.domain.autonomy import (
        clear_tenant_autonomy,
        grants_for_tenant,
        set_tenant_autonomy,
    )

    clear_tenant_autonomy()

    def fail(_url: str):
        raise psycopg.errors.UndefinedTable("tenant_autonomy")

    monkeypatch.setattr("factory_os.domain.postgres.connect", fail)
    tenant = uuid4()
    set_tenant_autonomy(
        tenant,
        industry="ropa",
        action="reply_customer",
        level="approval",
        url="postgresql://unused",
    )
    reply = next(
        item
        for item in grants_for_tenant(tenant, industry="ropa", url="postgresql://unused")
        if item.action == "reply_customer"
    )
    assert reply.level == "approval"
