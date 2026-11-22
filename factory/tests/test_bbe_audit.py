import pytest

from factory_os.contracts.employees import identity_for
from factory_os.domain.models import EmployeeRole, PILOT_TENANT_ID
from factory_os.harness.bbe import BBE_DENY, BBE_OK, BBEViolation
from factory_os.harness.tools import PermissionDenied
from tests.conftest import make_shop


def test_bbe_deny_is_recorded_and_handler_does_not_run() -> None:
    shop = make_shop()
    catalog = identity_for(EmployeeRole.CATALOG_ADMIN, PILOT_TENANT_ID)
    before = shop.tools.handler_calls
    with pytest.raises(BBEViolation):
        shop.tools.execute(
            catalog,
            "catalog.search",
            {"query": "blusa"},
            channel="whatsapp",
        )
    assert shop.tools.handler_calls == before
    deny = shop.tools.bbe_audit.events[-1]
    assert deny.decision == BBE_DENY
    assert deny.tool == "catalog.search"
    assert deny.channel == "whatsapp"
    assert deny.reason == "no_customer_whatsapp"
    assert deny.role == EmployeeRole.CATALOG_ADMIN.value


def test_bbe_ok_is_recorded_on_allowed_read() -> None:
    shop = make_shop()
    adri = identity_for(EmployeeRole.SALES, PILOT_TENANT_ID)
    shop.tools.execute(adri, "catalog.search", {"query": "blusa"})
    ok = shop.tools.bbe_audit.events[-1]
    assert ok.decision == BBE_OK
    assert ok.tool == "catalog.search"
    assert ok.reason is None


def test_permission_deny_does_not_reach_bbe_audit() -> None:
    shop = make_shop()
    adri = identity_for(EmployeeRole.SALES, PILOT_TENANT_ID)
    with pytest.raises(PermissionDenied):
        shop.tools.execute(adri, "payment.create_qr", {"order_id": "x"})
    assert shop.tools.bbe_audit.events == []
