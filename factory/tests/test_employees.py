import pytest

from factory_os.contracts.employees import EMPLOYEE_REGISTRY, ROLE_PERMISSIONS, identity_for
from factory_os.domain.models import EmployeeRole, PILOT_TENANT_ID
from factory_os.harness.bbe import BBEViolation
from factory_os.harness.model_gateway import DraftResult, FakeGateway
from factory_os.harness.policy import PolicyDenied
from factory_os.harness.tools import ConfirmationRequired, PermissionDenied
from tests.conftest import make_shop

SKU = "h001-M-VP"


def test_registry_has_seven_employees() -> None:
    assert len(EMPLOYEE_REGISTRY) == 10
    catalog = next(item for item in EMPLOYEE_REGISTRY if item.key == "catalog_admin")
    assert catalog.customer_whatsapp is False
    inventory = next(item for item in EMPLOYEE_REGISTRY if item.key == "inventory")
    assert inventory.customer_whatsapp is False


def test_coordinator_routes_postventa_and_keeps_payment_on_cobros() -> None:
    shop = make_shop()
    damaged = shop.handle_turn(shop.store.tenant_id, "59180000001", "Mi pedido llegó roto.")
    assert damaged.employee == "Postventa"
    assert "garantía" in damaged.reply.lower() or "garantia" in damaged.reply.lower() or "invent" in damaged.reply.lower()

    shop.handle_turn(shop.store.tenant_id, "59180000002", "quiero una blusa de seda")
    shop.handle_turn(shop.store.tenant_id, "59180000002", "confirmo")
    paid = shop.handle_turn(shop.store.tenant_id, "59180000002", "ya pagué")
    assert paid.employee == "Cobros"
    assert "no alcanza" in paid.reply.lower() or "pendiente" in paid.reply.lower()


def test_postventa_repeat_purchase_handoff_to_adri() -> None:
    shop = make_shop()
    shop.handle_turn(shop.store.tenant_id, "59180000003", "quiero una blusa de seda")
    result = shop.handle_turn(
        shop.store.tenant_id, "59180000003", "Mi pedido llegó ayer y necesito otro igual."
    )
    assert result.employee == "Postventa"
    assert "Adri" in result.reply
    conv = shop.store.list_conversations(shop.store.tenant_id)[0]
    assert conv.state.handoff is EmployeeRole.SALES


def test_inventory_stock_and_authorized_adjust() -> None:
    shop = make_shop()
    inquiry = shop.handle_staff(shop.store.tenant_id, EmployeeRole.INVENTORY, f"stock {SKU}")
    assert inquiry.employee == "Inventario"
    assert "stock" in inquiry.reply.lower()
    before = shop.store.get_variant(shop.store.tenant_id, SKU)
    assert before is not None
    start = before.stock
    adjusted = shop.handle_staff(shop.store.tenant_id, EmployeeRole.INVENTORY, f"ajustar {SKU} -1")
    assert str(start - 1) in adjusted.reply
    after = shop.store.get_variant(shop.store.tenant_id, SKU)
    assert after is not None
    assert after.stock == start - 1


def test_catalog_admin_create_and_disable() -> None:
    shop = make_shop()
    created = shop.handle_staff(
        shop.store.tenant_id, EmployeeRole.CATALOG_ADMIN, "alta AC-STAFF-NEW-001 15 BOB"
    )
    assert created.employee == "Catálogo"
    assert "AC-STAFF-NEW-001" in created.reply
    disabled = shop.handle_staff(
        shop.store.tenant_id, EmployeeRole.CATALOG_ADMIN, "desactivar AC-STAFF-NEW-001"
    )
    assert "desactiv" in disabled.reply.lower()


def test_catalog_admin_denied_on_customer_whatsapp() -> None:
    shop = make_shop()
    result = shop.handle_turn(shop.store.tenant_id, "59180000004", "alta AC-STAFF-HACK-001 15")
    assert result.employee != "Catálogo"


def test_security_frontiers_do_not_run_handlers() -> None:
    shop = make_shop()
    adri = identity_for(EmployeeRole.SALES, PILOT_TENANT_ID)
    cobros = identity_for(EmployeeRole.COBROS, PILOT_TENANT_ID)
    ops = identity_for(EmployeeRole.OPS, PILOT_TENANT_ID)
    postventa = identity_for(EmployeeRole.POSTVENTA, PILOT_TENANT_ID)
    inventory = identity_for(EmployeeRole.INVENTORY, PILOT_TENANT_ID)
    catalog = identity_for(EmployeeRole.CATALOG_ADMIN, PILOT_TENANT_ID)

    before = shop.tools.handler_calls
    with pytest.raises(PermissionDenied):
        shop.tools.execute(adri, "payment.create_qr", {"order_id": "x"})
    with pytest.raises(PermissionDenied):
        shop.tools.execute(adri, "catalog.upsert", {"variant_sku": SKU, "name": "x"})
    with pytest.raises(PermissionDenied):
        shop.tools.execute(cobros, "catalog.upsert", {"variant_sku": SKU, "name": "x"})
    with pytest.raises(PermissionDenied):
        shop.tools.execute(cobros, "order.create", {"variant_sku": SKU, "customer_id": "x"})
    with pytest.raises(PermissionDenied):
        shop.tools.execute(ops, "payment.create_qr", {"order_id": "x"})
    with pytest.raises(PermissionDenied):
        shop.tools.execute(postventa, "order.create", {"variant_sku": SKU, "customer_id": "x"})
    with pytest.raises(PermissionDenied):
        shop.tools.execute(inventory, "order.create", {"variant_sku": SKU, "customer_id": "x"})
    with pytest.raises(BBEViolation):
        shop.tools.execute(
            catalog,
            "catalog.search",
            {"query": "blusa"},
            channel="whatsapp",
        )
    assert shop.tools.handler_calls == before

    with pytest.raises(PolicyDenied) as denied:
        shop.tools.execute(
            ops,
            "delivery.create",
            {"order_id": "dddddddd-dddd-dddd-dddd-dddddddddddd", "recipient_name": "Ana", "address": "Calle 1"},
        )
    assert denied.value.code == "unknown_order"

    with pytest.raises(ConfirmationRequired):
        shop.tools.execute(adri, "order.create", {"variant_sku": SKU, "customer_id": shop.store.tenant_id})

    assert "order.create" in ROLE_PERMISSIONS[EmployeeRole.SALES]
    assert "payment.create_qr" not in ROLE_PERMISSIONS[EmployeeRole.SALES]


class _LyingGateway:
    """Draft lies; WHO/WHAT propose still come from Fake (intent simulation for pytest)."""

    def __init__(self, text: str) -> None:
        self.text = text
        self._fake = FakeGateway()

    def propose(self, **kwargs):
        return self._fake.propose(**kwargs)

    def propose_who(self, **kwargs):
        return self._fake.propose_who(**kwargs)

    def draft(self, *, fallback: str, **_kwargs):
        return DraftResult(text=self.text, provider="script")


def _checkout_until_qr(shop) -> str:
    shop.handle_turn(shop.store.tenant_id, "59180000020", "quiero una blusa de seda")
    close = shop.handle_turn(shop.store.tenant_id, "59180000020", "confirmo")
    assert "QR:" in close.reply
    return close.reply


def test_cobros_draft_cannot_mark_paid_while_pending() -> None:
    shop = make_shop()
    _checkout_until_qr(shop)
    shop.gateway = _LyingGateway("El pago está confirmado por el banco. Listo.")
    pending = shop.handle_turn(shop.store.tenant_id, "59180000020", "ya pagué")
    assert pending.employee == "Cobros"
    lowered = pending.reply.lower()
    assert "pendiente" in lowered
    assert "confirmado por el banco" not in lowered


def test_ops_draft_cannot_invent_promo_on_ship() -> None:
    shop = make_shop()
    _checkout_until_qr(shop)
    conv = shop.store.list_conversations(shop.store.tenant_id)[0]
    ref = conv.state.provider_ref
    assert ref
    shop.confirm_payment_from_adapter(ref)
    shop.handle_turn(shop.store.tenant_id, "59180000020", "ya pagué")
    shop.gateway = _LyingGateway("Hay 20% de descuento y envio gratis. Envío listo.")
    ship = shop.handle_turn(shop.store.tenant_id, "59180000020", "me llamo Ana, vivo en Calle 10")
    assert ship.employee == "Operaciones"
    assert "20%" not in ship.reply
    assert "envio gratis" not in ship.reply.lower()
    assert "Envío registrado" in ship.reply or "pedido es #" in ship.reply.lower()
    assert "Ana" in ship.reply
    assert "#" in ship.reply


def test_postventa_draft_cannot_invent_warranty() -> None:
    shop = make_shop()
    shop.gateway = _LyingGateway("Tiene garantía de 90 días y te devolvemos el dinero.")
    damaged = shop.handle_turn(shop.store.tenant_id, "59180000021", "Mi pedido llegó roto.")
    assert damaged.employee == "Postventa"
    lowered = damaged.reply.lower()
    assert "90" not in damaged.reply
    assert "te devolvemos" not in lowered
    assert "invent" in lowered or "anoto" in lowered


def test_skill_does_not_unlock_payment() -> None:
    shop = make_shop()
    adri = identity_for(EmployeeRole.SALES, PILOT_TENANT_ID)
    before = shop.tools.handler_calls
    with pytest.raises(PermissionDenied):
        shop.tools.execute(adri, "payment.create_qr", {"order_id": "x"}, skill="sales_discovery")
    assert shop.tools.handler_calls == before
