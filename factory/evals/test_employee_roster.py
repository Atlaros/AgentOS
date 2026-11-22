"""Roster evals: disabled catalog roles stay off WhatsApp WHO; clones keep base tools."""

from factory_os.agents.orchestrator import choose_employee
from factory_os.agents.turn import ShopRuntime
from factory_os.contracts.employees import ROLE_PERMISSIONS, identity_for
from factory_os.domain.models import EmployeeRole, PILOT_TENANT_ID
from factory_os.domain.seed import catalog_seed_path, load_catalog_json
from factory_os.domain.store import MemoryCommerceStore
from factory_os.domain.tenant_employees import (
    clear_tenant_employees,
    clone_employee,
    ensure_tenant_roster,
    set_employee_enabled,
    set_employee_profile,
)
from factory_os.tools.registry import FakePaymentProvider


def _shop(kind: str = "cafe") -> ShopRuntime:
    store = MemoryCommerceStore(PILOT_TENANT_ID)
    load_catalog_json(catalog_seed_path(kind), store)
    clear_tenant_employees()
    ensure_tenant_roster(PILOT_TENANT_ID)
    return ShopRuntime(store, FakePaymentProvider())


def test_cafe_disabled_ops_does_not_attend_whatsapp() -> None:
    shop = _shop("cafe")
    set_employee_enabled(PILOT_TENANT_ID, "ops", False)
    result = shop.handle_turn(PILOT_TENANT_ID, "59171119001", "quiero empanadas")
    assert result.employee != "Operaciones"
    conv = shop.store.list_conversations(PILOT_TENANT_ID)[0]
    who = choose_employee(
        shop.store,
        conv,
        "necesito envío urgente",
        proposed=EmployeeRole.OPS,
        tenant_id=PILOT_TENANT_ID,
    )
    assert who is EmployeeRole.SALES


def test_closet_disabled_ops_does_not_attend_whatsapp() -> None:
    shop = _shop("closet")
    set_employee_enabled(PILOT_TENANT_ID, "ops", False)
    result = shop.handle_turn(PILOT_TENANT_ID, "59171119002", "busco una campera")
    assert result.employee != "Operaciones"
    assert result.employee


def test_renamed_sales_shows_display_name() -> None:
    shop = _shop("cafe")
    set_employee_profile(PILOT_TENANT_ID, "sales", display_name="Adri Norte")
    result = shop.handle_turn(PILOT_TENANT_ID, "59171119003", "hola")
    assert result.employee == "Adri Norte"
    assert identity_for(EmployeeRole.SALES, PILOT_TENANT_ID).employee_name == "Adri Norte"


def test_sales_clone_keeps_sales_permissions_only() -> None:
    clear_tenant_employees()
    ensure_tenant_roster(PILOT_TENANT_ID)
    clone = clone_employee(
        PILOT_TENANT_ID, base_role=EmployeeRole.SALES, display_name="Adri Promo"
    )
    assert clone.is_clone is True
    assert clone.base_role is EmployeeRole.SALES
    sales_tools = ROLE_PERMISSIONS[EmployeeRole.SALES]
    cobros_tools = ROLE_PERMISSIONS[EmployeeRole.COBROS]
    assert ROLE_PERMISSIONS[clone.base_role] == sales_tools
    assert ROLE_PERMISSIONS[clone.base_role] != cobros_tools
    assert "payments.confirm" not in sales_tools


def test_two_adri_clones_do_not_break_payment_confirm_path() -> None:
    shop = _shop("cafe")
    clone_employee(PILOT_TENANT_ID, base_role=EmployeeRole.SALES, display_name="Adri Promo")
    clone_employee(PILOT_TENANT_ID, base_role=EmployeeRole.SALES, display_name="Adri VIP")
    browse = shop.handle_turn(PILOT_TENANT_ID, "59171119004", "quiero empanadas")
    assert browse.employee in {"Adri", "Adri Promo", "Adri VIP"}
    shop.handle_turn(PILOT_TENANT_ID, "59171119004", "confirmo")
    conv = shop.store.list_conversations(PILOT_TENANT_ID)[0]
    ref = conv.state.provider_ref
    assert ref
    shop.confirm_payment_from_adapter(ref)
    paid = shop.handle_turn(PILOT_TENANT_ID, "59171119004", "ya pagué")
    assert "confirmado" in paid.reply.lower()
