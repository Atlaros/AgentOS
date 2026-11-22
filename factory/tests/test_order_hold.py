"""Unpaid orders hold the garment for 15 minutes, then disappear."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from factory_os.domain.catalog import search_catalog
from factory_os.domain.models import OrderItem, PILOT_TENANT_ID, PaymentStatus
from factory_os.domain.order_hold import release_expired_unpaid_orders
from factory_os.domain.seed import load_pilot_catalog
from factory_os.domain.store import MemoryCommerceStore


def _shop() -> MemoryCommerceStore:
    store = MemoryCommerceStore(PILOT_TENANT_ID)
    load_pilot_catalog(store)
    return store


def test_open_order_hides_garment_until_hold_expires() -> None:
    store = _shop()
    customer = store.get_or_create_customer(PILOT_TENANT_ID, "59170000001")
    customer.name = "Ana"
    customer.address = "Calle 1, La Paz"
    sku = "h001-M-VP"
    record = store.get_variant(PILOT_TENANT_ID, sku)
    assert record is not None
    order = store.create_order(
        PILOT_TENANT_ID,
        customer.id,
        OrderItem(sku, record.name, 1, record.price, record.currency),
    )
    assert sku in store.held_variant_skus(PILOT_TENANT_ID)
    hidden = search_catalog(store, PILOT_TENANT_ID, "h001")
    assert all(hit.variant_sku != sku for hit in hidden)
    order.created_at = datetime.now(UTC) - timedelta(minutes=16)
    assert release_expired_unpaid_orders(store, PILOT_TENANT_ID) == 1
    assert store.get_order(PILOT_TENANT_ID, order.id) is None
    assert sku not in store.held_variant_skus(PILOT_TENANT_ID)
    again = search_catalog(store, PILOT_TENANT_ID, "h001")
    assert again and again[0].variant_sku == sku


def test_confirmed_payment_is_not_deleted() -> None:
    store = _shop()
    customer = store.get_or_create_customer(PILOT_TENANT_ID, "59170000002")
    sku = "h001-M-VP"
    record = store.get_variant(PILOT_TENANT_ID, sku)
    assert record is not None
    order = store.create_order(
        PILOT_TENANT_ID,
        customer.id,
        OrderItem(sku, record.name, 1, record.price, record.currency),
    )
    payment = store.create_payment(
        PILOT_TENANT_ID, order.id, "baneco", "ref-1", Decimal(str(record.price)), "BOB", "img"
    )
    payment.status = PaymentStatus.CONFIRMED
    order.created_at = datetime.now(UTC) - timedelta(minutes=30)
    assert release_expired_unpaid_orders(store, PILOT_TENANT_ID) == 0
    assert store.get_order(PILOT_TENANT_ID, order.id) is not None
    assert sku not in store.held_variant_skus(PILOT_TENANT_ID)


def test_walkin_qr_payment_is_not_deleted_and_pending_ticket_expires() -> None:
    """Cash-sale QR payments have order_id=None but FK from cash_sale_tickets — never DELETE."""
    from factory_os.domain.cash_sales import create_walkin_qr_sale
    from factory_os.tools.payments import FakePaymentProvider
    from tests.conftest import make_shop

    shop = make_shop()
    store = shop.store
    store.open_cash_session(PILOT_TENANT_ID, Decimal("0"), "BOB", "test", None)
    ticket, _qr = create_walkin_qr_sale(
        store,
        FakePaymentProvider(),
        PILOT_TENANT_ID,
        lines=[("h001-M-VP", 1)],
        recorded_by_name="caja",
    )
    assert ticket.status == "pending_qr"
    assert ticket.payment_id is not None
    payment = store.get_payment(PILOT_TENANT_ID, ticket.payment_id)
    assert payment is not None
    payment.created_at = datetime.now(UTC) - timedelta(minutes=20)
    ticket.created_at = payment.created_at

    released = release_expired_unpaid_orders(store, PILOT_TENANT_ID)
    assert released >= 1
    assert store.get_payment(PILOT_TENANT_ID, ticket.payment_id) is not None
    refreshed = store.get_cash_sale_ticket(PILOT_TENANT_ID, ticket.id)
    assert refreshed is not None
    assert refreshed.status == "voided"
    assert store.get_payment(PILOT_TENANT_ID, ticket.payment_id).status is PaymentStatus.EXPIRED
    assert "h001-M-VP" not in store.held_variant_skus(PILOT_TENANT_ID)
