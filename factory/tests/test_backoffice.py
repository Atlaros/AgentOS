import pytest

from factory_os.contracts.employees import ROLE_PERMISSIONS, identity_for
from factory_os.domain.models import EmployeeRole, PILOT_TENANT_ID
from factory_os.harness.tools import PermissionDenied
from tests.conftest import make_shop

SKU = "h001-M-VP"


def test_accounting_records_cash_not_qr() -> None:
    shop = make_shop()
    entrada = shop.handle_staff(shop.store.tenant_id, EmployeeRole.ACCOUNTING, "entrada 50 venta mostrador")
    assert entrada.employee == "Contabilidad"
    assert "50" in entrada.reply
    assert "QR" in entrada.reply or "qr" in entrada.reply.lower() or "cobro" in entrada.reply.lower()
    ledger = shop.handle_staff(shop.store.tenant_id, EmployeeRole.ACCOUNTING, "arqueo de caja")
    assert "50" in ledger.reply
    cobros = identity_for(EmployeeRole.COBROS, PILOT_TENANT_ID)
    accounting = identity_for(EmployeeRole.ACCOUNTING, PILOT_TENANT_ID)
    assert "payment.create_qr" in ROLE_PERMISSIONS[EmployeeRole.COBROS]
    assert "payment.create_qr" not in ROLE_PERMISSIONS[EmployeeRole.ACCOUNTING]
    before = shop.tools.handler_calls
    with pytest.raises(PermissionDenied):
        shop.tools.execute(accounting, "payment.create_qr", {"order_id": "x"})
    with pytest.raises(PermissionDenied):
        shop.tools.execute(cobros, "cash.record", {"direction": "in", "amount": "1"})
    assert shop.tools.handler_calls == before


def test_analyst_reads_metrics() -> None:
    shop = make_shop()
    shop.handle_turn(shop.store.tenant_id, "59190000001", "quiero una blusa de seda")
    shop.handle_turn(shop.store.tenant_id, "59190000001", "confirmo")
    conv = shop.store.list_conversations(shop.store.tenant_id)[0]
    assert conv.state.provider_ref
    shop.confirm_payment_from_adapter(conv.state.provider_ref)
    result = shop.handle_staff(shop.store.tenant_id, EmployeeRole.ANALYST, "métricas del negocio")
    assert result.employee == "Analista"
    assert "Pedidos: 1" in result.reply
    analyst = identity_for(EmployeeRole.ANALYST, PILOT_TENANT_ID)
    before = shop.tools.handler_calls
    with pytest.raises(PermissionDenied):
        shop.tools.execute(analyst, "order.create", {"variant_sku": SKU, "customer_id": "x"})
    assert shop.tools.handler_calls == before


def test_suppliers_receive_stock_and_do_not_message_vendor() -> None:
    shop = make_shop()
    before = shop.store.get_variant(shop.store.tenant_id, SKU)
    assert before is not None
    start = before.stock
    received = shop.handle_staff(
        shop.store.tenant_id, EmployeeRole.SUPPLIERS, f"recibir {SKU} 4"
    )
    assert received.employee == "Proveedores"
    assert "+4" in received.reply
    after = shop.store.get_variant(shop.store.tenant_id, SKU)
    assert after is not None
    assert after.stock == start + 4
    alert = shop.handle_staff(shop.store.tenant_id, EmployeeRole.SUPPLIERS, "no hay stock")
    assert "proveedor" in alert.reply.lower()
    assert "todavía" in alert.reply.lower() or "despues" in alert.reply.lower() or "después" in alert.reply.lower()
    suppliers = identity_for(EmployeeRole.SUPPLIERS, PILOT_TENANT_ID)
    with pytest.raises(PermissionDenied):
        shop.tools.execute(suppliers, "payment.create_qr", {"order_id": "x"})


def test_customer_whatsapp_does_not_reach_backoffice() -> None:
    shop = make_shop()
    result = shop.handle_turn(shop.store.tenant_id, "59190000002", "métricas del negocio")
    assert result.employee not in {"Contabilidad", "Analista", "Proveedores"}
