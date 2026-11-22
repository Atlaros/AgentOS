"""Published catalog rules react to store facts without confirming payment."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

from factory_os.domain.flow_canvas import clear_rules, create_rule, publish_rule
from factory_os.domain.models import OrderItem, PILOT_TENANT_ID, PaymentStatus
from factory_os.domain.rule_runtime import clear_rule_runtime, run_published_rules
from factory_os.tools.channel import FakeChannel
from tests.conftest import make_shop, owner_client

DIGEST_NOW = datetime(2026, 11, 11, 16, 0, tzinfo=UTC)


def test_qr_pending_rule_notifies_owner_once() -> None:
    clear_rules()
    clear_rule_runtime()
    shop = make_shop()
    store = shop.store
    customer = store.get_or_create_customer(PILOT_TENANT_ID, "59170001111")
    variant = next(iter(store.variants.values()))
    order = store.create_order(
        PILOT_TENANT_ID,
        customer.id,
        OrderItem(
            variant.variant_sku,
            variant.name,
            1,
            variant.price,
            variant.currency,
        ),
        status="reserved",
    )
    payment = store.create_payment(
        PILOT_TENANT_ID,
        order.id,
        "fake",
        "qr-stale-1",
        variant.price,
        variant.currency,
        "QR:stale",
        customer_id=customer.id,
    )
    payment.created_at = datetime.now(UTC) - timedelta(hours=30)
    assert payment.status is PaymentStatus.PENDING

    rule = create_rule(
        when_event="qr_pending",
        if_threshold="hours>24",
        then_action="notify_owner",
        tenant_id=PILOT_TENANT_ID,
    )
    publish_rule(rule.id)

    channel = FakeChannel()
    first = run_published_rules(
        store,
        PILOT_TENANT_ID,
        channel=channel,
        owner_numbers=["59170009999"],
    )
    assert len(first) == 1
    assert first[0]["action"] == "notify_owner"
    assert first[0]["notified"] == 1
    assert first[0]["sent"] == 1
    assert "confirm" not in first[0]["text"].lower()
    assert len(channel.sent) == 1

    second = run_published_rules(
        store,
        PILOT_TENANT_ID,
        channel=channel,
        owner_numbers=["59170009999"],
    )
    assert second == []
    assert len(channel.sent) == 1


def test_stock_low_rule_drafts_purchase_order_once() -> None:
    clear_rules()
    clear_rule_runtime()
    shop = make_shop()
    store = shop.store
    supplier = store.create_supplier(PILOT_TENANT_ID, name="Regla Sur")
    variant = next(iter(store.variants.values()))
    store.set_variant_supplier(PILOT_TENANT_ID, variant.variant_sku, supplier.id)
    store.set_reorder_threshold(PILOT_TENANT_ID, variant.variant_sku, 5)
    store.adjust_stock(PILOT_TENANT_ID, variant.variant_sku, -max(0, variant.stock - 1))

    rule = create_rule(
        when_event="stock_low",
        if_threshold="below_minimum",
        then_action="draft_purchase_order",
        tenant_id=PILOT_TENANT_ID,
    )
    publish_rule(rule.id)

    first = run_published_rules(store, PILOT_TENANT_ID)
    assert len(first) == 1
    assert first[0]["action"] == "draft_purchase_order"
    assert first[0]["status"] == "ok"
    assert first[0]["purchase_order_ids"]
    drafts = store.list_purchase_orders(PILOT_TENANT_ID, status="draft")
    assert len(drafts) == 1
    assert drafts[0].notes == "rule:stock_low"

    second = run_published_rules(store, PILOT_TENANT_ID)
    assert second == []
    assert len(store.list_purchase_orders(PILOT_TENANT_ID, status="draft")) == 1


def test_rules_run_endpoint_executes_for_tenant() -> None:
    clear_rules()
    clear_rule_runtime()
    shop = make_shop()
    store = shop.store
    customer = store.get_or_create_customer(PILOT_TENANT_ID, "59170002222")
    variant = next(iter(store.variants.values()))
    order = store.create_order(
        PILOT_TENANT_ID,
        customer.id,
        OrderItem(variant.variant_sku, variant.name, 1, variant.price, variant.currency),
        status="reserved",
    )
    payment = store.create_payment(
        PILOT_TENANT_ID,
        order.id,
        "fake",
        "qr-api-1",
        variant.price,
        variant.currency,
        "QR:api",
        customer_id=customer.id,
    )
    payment.created_at = datetime.now(UTC) - timedelta(hours=40)
    rule = create_rule(
        when_event="qr_pending",
        if_threshold="hours>24",
        then_action="notify_owner",
        tenant_id=PILOT_TENANT_ID,
    )
    publish_rule(rule.id)

    client = owner_client(shop)
    response = client.post("/api/rules/run")
    assert response.status_code == 200
    body = response.json()
    assert body["fired"] == 1
    assert body["results"][0]["action"] == "notify_owner"


def test_owner_digest_rule_sends_analytics_digest_once() -> None:
    clear_rules()
    clear_rule_runtime()
    shop = make_shop()
    channel = FakeChannel()
    owners = ["59170009999"]
    thresholds = shop.store.get_analytics_thresholds(PILOT_TENANT_ID)
    shop.store.put_analytics_thresholds(
        PILOT_TENANT_ID,
        replace(thresholds, digest_whatsapp_enabled=True),
    )
    records = list(shop.store.iter_variants())
    for record in records:
        record.stock = 8
        record.reorder_threshold = 1
    records[0].stock = 0

    rule = create_rule(
        when_event="owner_digest",
        if_threshold="has_alerts",
        then_action="notify_owner",
        tenant_id=PILOT_TENANT_ID,
    )
    publish_rule(rule.id)

    first = run_published_rules(
        shop.store,
        PILOT_TENANT_ID,
        channel=channel,
        owner_numbers=owners,
        now=DIGEST_NOW,
    )
    assert len(first) == 1
    assert first[0]["event"] == "owner_digest"
    assert first[0]["action"] == "notify_owner"
    assert first[0]["status"] == "sent"
    assert first[0]["sent"] == 1
    assert "confirm" not in str(first[0].get("digest", {})).lower()
    assert len(channel.sent) == 1
    assert "Stock bajo" in channel.sent[0][1]

    second = run_published_rules(
        shop.store,
        PILOT_TENANT_ID,
        channel=channel,
        owner_numbers=owners,
        now=DIGEST_NOW,
    )
    assert second == []
    assert len(channel.sent) == 1


def test_payment_overdue_rule_notifies_owner_once() -> None:
    clear_rules()
    clear_rule_runtime()
    shop = make_shop()
    store = shop.store
    customer = store.get_or_create_customer(PILOT_TENANT_ID, "59170003333")
    variant = next(iter(store.variants.values()))
    order = store.create_order(
        PILOT_TENANT_ID,
        customer.id,
        OrderItem(
            variant.variant_sku,
            variant.name,
            1,
            variant.price,
            variant.currency,
        ),
        status="reserved",
    )
    payment = store.create_payment(
        PILOT_TENANT_ID,
        order.id,
        "fake",
        "qr-expired-1",
        variant.price,
        variant.currency,
        "QR:expired",
        customer_id=customer.id,
    )
    payment.status = PaymentStatus.EXPIRED

    rule = create_rule(
        when_event="payment_overdue",
        if_threshold="expired",
        then_action="notify_owner",
        tenant_id=PILOT_TENANT_ID,
    )
    publish_rule(rule.id)

    channel = FakeChannel()
    first = run_published_rules(
        store,
        PILOT_TENANT_ID,
        channel=channel,
        owner_numbers=["59170009999"],
    )
    assert len(first) == 1
    assert first[0]["action"] == "notify_owner"
    assert first[0]["event"] == "payment_overdue"
    assert first[0]["notified"] == 1
    assert "confirm" not in first[0]["text"].lower()
    assert "vencido" in first[0]["text"].lower()
    assert len(channel.sent) == 1

    second = run_published_rules(
        store,
        PILOT_TENANT_ID,
        channel=channel,
        owner_numbers=["59170009999"],
    )
    assert second == []
    assert len(channel.sent) == 1


def test_customer_inactive_rule_notifies_owner_once() -> None:
    clear_rules()
    clear_rule_runtime()
    shop = make_shop()
    store = shop.store
    now = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
    customer = store.get_or_create_customer(PILOT_TENANT_ID, "59170004444")
    conv = store.get_or_create_conversation(PILOT_TENANT_ID, customer)
    conv.last_message_at = now - timedelta(days=45)
    store.save_conversation_state(conv)

    rule = create_rule(
        when_event="customer_inactive",
        if_threshold="days>30",
        then_action="notify_owner",
        tenant_id=PILOT_TENANT_ID,
    )
    publish_rule(rule.id)

    channel = FakeChannel()
    first = run_published_rules(
        store,
        PILOT_TENANT_ID,
        channel=channel,
        owner_numbers=["59170009999"],
        now=now,
    )
    assert len(first) == 1
    assert first[0]["action"] == "notify_owner"
    assert first[0]["event"] == "customer_inactive"
    assert first[0]["notified"] >= 1
    assert "confirm" not in first[0]["text"].lower()
    assert len(channel.sent) == 1

    second = run_published_rules(
        store,
        PILOT_TENANT_ID,
        channel=channel,
        owner_numbers=["59170009999"],
        now=now,
    )
    assert second == []
    assert len(channel.sent) == 1


def test_owner_digest_rule_skips_when_digest_disabled() -> None:
    clear_rules()
    clear_rule_runtime()
    shop = make_shop()
    channel = FakeChannel()
    thresholds = shop.store.get_analytics_thresholds(PILOT_TENANT_ID)
    shop.store.put_analytics_thresholds(
        PILOT_TENANT_ID,
        replace(thresholds, digest_whatsapp_enabled=False),
    )
    records = list(shop.store.iter_variants())
    records[0].stock = 0
    records[0].reorder_threshold = 1

    rule = create_rule(
        when_event="owner_digest",
        if_threshold="has_alerts",
        then_action="notify_owner",
        tenant_id=PILOT_TENANT_ID,
    )
    publish_rule(rule.id)

    fired = run_published_rules(
        shop.store,
        PILOT_TENANT_ID,
        channel=channel,
        owner_numbers=["59170009999"],
        now=DIGEST_NOW,
    )
    assert fired == []
    assert channel.sent == []
