from factory_os.agents.orchestrator import choose_employee
from factory_os.domain.models import EmployeeRole, PILOT_TENANT_ID, Payment, PaymentStatus
from factory_os.domain.store import MemoryCommerceStore
from factory_os.domain.models import Conversation, Customer
from uuid import uuid4


def test_default_route_is_sales() -> None:
    store = MemoryCommerceStore(PILOT_TENANT_ID)
    customer = store.get_or_create_customer(PILOT_TENANT_ID, "5917")
    conv = store.get_or_create_conversation(PILOT_TENANT_ID, customer)
    assert choose_employee(store, conv, "quiero una blusa") is EmployeeRole.SALES


def test_unpaid_order_pay_phrase_goes_to_cobros() -> None:
    store = MemoryCommerceStore(PILOT_TENANT_ID)
    customer = store.get_or_create_customer(PILOT_TENANT_ID, "5917")
    conv = store.get_or_create_conversation(PILOT_TENANT_ID, customer)
    conv.state.order_id = uuid4()
    conv.state.handoff = EmployeeRole.COBROS
    assert choose_employee(store, conv, "ya pagué el qr") is EmployeeRole.COBROS


def test_paid_order_shipping_goes_to_ops() -> None:
    store = MemoryCommerceStore(PILOT_TENANT_ID)
    customer = store.get_or_create_customer(PILOT_TENANT_ID, "5917")
    conv = store.get_or_create_conversation(PILOT_TENANT_ID, customer)
    order_id = uuid4()
    conv.state.order_id = order_id
    payment_id = uuid4()
    conv.state.payment_id = payment_id
    store.payments[payment_id] = Payment(
        id=payment_id,
        tenant_id=PILOT_TENANT_ID,
        order_id=order_id,
        provider="fake",
        provider_ref="r1",
        amount=1,
        currency="BOB",
        status=PaymentStatus.CONFIRMED,
        qr_payload="QR",
    )
    assert choose_employee(store, conv, "me llamo Ana vivo en Calle 1") is EmployeeRole.OPS
