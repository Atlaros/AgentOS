"""Cart stays unpaid until the pay intent. One QR charges the quoted total."""

from decimal import Decimal

from factory_os.domain.cart_quote import hold_minutes_for, quote_lines
from factory_os.domain.models import PILOT_TENANT_ID
from factory_os.harness.model_gateway import ActionProposal, DraftResult, FakeGateway
from factory_os.domain.models import NextAction
from tests.conftest import make_shop, owner_client


def _hit(store, sku: str) -> dict:
    record = store.get_variant(PILOT_TENANT_ID, sku)
    assert record is not None
    return {
        "variant_sku": record.variant_sku,
        "codigo": record.product_sku,
        "name": record.name,
        "price": str(record.price),
        "currency": record.currency,
        "stock": record.stock,
    }


def test_three_garments_discount_five_each() -> None:
    quote = quote_lines(
        [
            {"name": "a", "quantity": 1, "unit_price": "100", "currency": "BOB"},
            {"name": "b", "quantity": 1, "unit_price": "80", "currency": "BOB"},
            {"name": "c", "quantity": 1, "unit_price": "40", "currency": "BOB"},
        ]
    )
    assert quote.garment_count == 3
    assert quote.discount == Decimal("15")
    assert quote.total == Decimal("205")
    assert hold_minutes_for("h001") == 15
    assert hold_minutes_for(None) == 20


def test_adding_to_cart_does_not_issue_qr() -> None:
    shop = make_shop()
    wa = "59170008801"
    customer = shop.store.get_or_create_customer(PILOT_TENANT_ID, wa)
    conv = shop.store.get_or_create_conversation(PILOT_TENANT_ID, customer)
    hit = _hit(shop.store, "pago1-U-B")
    conv.state.considered_variant_sku = str(hit["variant_sku"])
    conv.state.last_hits = [hit]
    shop.store.save_conversation_state(conv)

    result = shop.handle_turn(PILOT_TENANT_ID, wa, "agregalo al carrito")
    conv = shop.store.get_conversation(PILOT_TENANT_ID, conv.id)
    assert conv is not None
    assert conv.state.provider_ref is None
    assert conv.state.order_id is None
    assert len(conv.state.cart) == 1
    assert "carrito" in result.reply.lower()
    assert "Para pagar" not in result.reply


def test_checkout_quotes_cart_and_shows_it_on_the_api() -> None:
    shop = make_shop()
    wa = "59170008802"
    customer = shop.store.get_or_create_customer(PILOT_TENANT_ID, wa)
    conv = shop.store.get_or_create_conversation(PILOT_TENANT_ID, customer)
    skus = ("pago1-U-B", "pago2-U-N", "h001-M-VP")
    hits = [_hit(shop.store, sku) for sku in skus]
    conv.state.cart = [
        {
            "variant_sku": hit["variant_sku"],
            "name": hit["name"],
            "quantity": 1,
            "price": hit["price"],
            "currency": hit["currency"],
        }
        for hit in hits
    ]
    conv.state.considered_variant_sku = str(hits[0]["variant_sku"])
    conv.state.last_hits = hits
    shop.store.save_conversation_state(conv)

    result = shop.handle_turn(PILOT_TENANT_ID, wa, "confirmo")
    conv = shop.store.get_conversation(PILOT_TENANT_ID, conv.id)
    assert conv is not None and conv.state.order_id is not None
    order = shop.store.get_order(PILOT_TENANT_ID, conv.state.order_id)
    assert order is not None
    assert order.status == "reserved"
    assert len(order.items) == 3
    assert order.discount_amount == Decimal("15")
    assert order.hold_minutes == 20
    payment = shop.store.payment_for_order(PILOT_TENANT_ID, order.id)
    assert payment is not None
    subtotal = sum(item.unit_price for item in order.items)
    assert payment.amount == subtotal - Decimal("15")
    assert "Total a pagar" in result.reply
    assert "Descuento de 5" in result.reply
    assert "20 minutos" in result.reply

    client = owner_client(shop)
    row = next(item for item in client.get("/api/orders").json()["orders"] if item["id"] == str(order.id))
    assert row["discount"] == "15"
    assert Decimal(row["total"]) == payment.amount
    detail = client.get(f"/api/conversations/{conv.id}").json()
    assert detail["cart"]["garment_count"] == 3
    assert Decimal(detail["cart"]["discount"]) == Decimal("15")


def test_live_code_hold_is_fifteen_minutes() -> None:
    shop = make_shop()
    wa = "59170008803"
    customer = shop.store.get_or_create_customer(PILOT_TENANT_ID, wa)
    conv = shop.store.get_or_create_conversation(PILOT_TENANT_ID, customer)
    hit = _hit(shop.store, "pago2-U-N")
    conv.state.considered_variant_sku = str(hit["variant_sku"])
    conv.state.last_hits = [hit]
    conv.live_code = "pago2"
    shop.store.save_conversation_state(conv)
    shop.handle_turn(PILOT_TENANT_ID, wa, "confirmo")
    conv = shop.store.get_conversation(PILOT_TENANT_ID, conv.id)
    assert conv is not None and conv.state.order_id is not None
    order = shop.store.get_order(PILOT_TENANT_ID, conv.state.order_id)
    assert order is not None and order.hold_minutes == 15
    assert order.discount_amount == Decimal("0")


def test_cart_change_reissues_one_qr() -> None:
    shop = make_shop()
    wa = "59170008804"
    customer = shop.store.get_or_create_customer(PILOT_TENANT_ID, wa)
    conv = shop.store.get_or_create_conversation(PILOT_TENANT_ID, customer)
    first = _hit(shop.store, "pago1-U-B")
    second = _hit(shop.store, "pago2-U-N")
    conv.state.considered_variant_sku = str(first["variant_sku"])
    conv.state.last_hits = [first]
    shop.store.save_conversation_state(conv)
    shop.handle_turn(PILOT_TENANT_ID, wa, "confirmo")
    conv = shop.store.get_conversation(PILOT_TENANT_ID, conv.id)
    assert conv is not None and conv.state.order_id is not None
    first_order = conv.state.order_id

    class AddSecond(FakeGateway):
        def propose_who(self, **_kwargs):
            return "sales"

        def propose(self, *, role, **_kwargs):
            if str(role).lower() in {"sales", "adri"}:
                return ActionProposal(
                    NextAction.ADD_TO_CART,
                    "sales_closing",
                    arguments={"tool": "cart.add"},
                    provider="fake",
                )
            return super().propose(role=role, context="", text="", state=conv.state)

    conv.state.considered_variant_sku = str(second["variant_sku"])
    conv.state.last_hits = [first, second]
    shop.store.save_conversation_state(conv)
    shop.gateway = AddSecond()
    result = shop.handle_turn(PILOT_TENANT_ID, wa, "sumá el otro")
    conv = shop.store.get_conversation(PILOT_TENANT_ID, conv.id)
    assert conv is not None and conv.state.order_id is not None
    assert conv.state.order_id != first_order
    assert shop.store.get_order(PILOT_TENANT_ID, first_order) is None
    order = shop.store.get_order(PILOT_TENANT_ID, conv.state.order_id)
    assert order is not None and len(order.items) == 2
    assert "total nuevo" in result.reply.lower() or "Total a pagar" in result.reply
