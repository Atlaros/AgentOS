"""Disabled roster roles must not win WHO (ADR-026)."""

from __future__ import annotations

from factory_os.agents.orchestrator import choose_employee
from factory_os.domain.models import EmployeeRole, PILOT_TENANT_ID
from factory_os.domain.provision import provision_business
from factory_os.domain.store import MemoryCommerceStore
from factory_os.domain.tenant_employees import set_employee_enabled


def test_disabled_ops_never_chosen_for_whatsapp() -> None:
    tid = provision_business(name="Who Ops", industry="cafe")
    store = MemoryCommerceStore(tid)
    set_employee_enabled(tid, "ops", False)
    customer = store.get_or_create_customer(tid, "59170001111")
    conversation = store.get_or_create_conversation(tid, customer)
    conversation.state.channel = "whatsapp"
    conversation.state.order_id = None
    who = choose_employee(
        store,
        conversation,
        "quiero envío",
        proposed=EmployeeRole.OPS,
        tenant_id=tid,
    )
    assert who is not EmployeeRole.OPS
    assert who is EmployeeRole.SALES


def test_enabled_postventa_still_reachable() -> None:
    tid = provision_business(name="Who Post", industry="cafe")
    store = MemoryCommerceStore(tid)
    customer = store.get_or_create_customer(tid, "59170002222")
    conversation = store.get_or_create_conversation(tid, customer)
    conversation.state.channel = "whatsapp"
    who = choose_employee(
        store,
        conversation,
        "llegó roto",
        proposed=EmployeeRole.POSTVENTA,
        tenant_id=tid,
    )
    assert who is EmployeeRole.POSTVENTA
