from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import re
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path
from uuid import UUID

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, Response, StreamingResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from factory_os.agents.turn import ShopRuntime
from factory_os.domain.catalog_xlsx import make_variant_sku
from factory_os.domain.models import Conversation, Customer, PILOT_TENANT_ID, PaymentStatus
from factory_os.domain.seed import catalog_seed_path, extra_seed_paths, load_catalog_json, tokenize
from factory_os.domain.store import MemoryCommerceStore, VariantRecord
from factory_os.domain.postgres import open_postgres_shop
from factory_os.harness.model_gateway import GatewaySettings, build_gateway
from factory_os.tools.channel import FakeChannel, MetaChannel, parse_inbound
from factory_os.tools.inbound_buffer import (
    DEFAULT_DEBOUNCE_S,
    InboundBuffer,
    MemoryInboundBuffer,
    build_inbound_buffer,
)
from factory_os.tools.inbound_dedup import InboundDeduper, MemoryInboundDeduper, build_inbound_deduper

INBOX_PATH = Path(__file__).resolve().parent / "static" / "inbox.html"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Development bypasses must be opted into explicitly; an unset environment
    # is treated as hosted by every local/test-mode guard below.
    app_env: str = ""
    redis_url: str = "redis://localhost:6379/0"
    database_url: str = ""
    database_runtime_url: str = ""
    catalog_seed: str = "closet"
    model_provider: str = "fake"
    google_api_key: str = ""
    gemini_default_model_id: str = ""
    model_secondary_provider: str = ""
    openrouter_api_key: str = ""
    openrouter_model_id: str = ""
    groq_api_key: str = ""
    groq_model_id: str = ""
    cohere_api_key: str = ""
    cohere_embed_model_id: str = "embed-v4.0"
    cohere_embed_dims: int = 1024
    model_timeout_s: float = 8.0
    frontend_origin: str = "http://localhost:3000"
    public_base_url: str = "http://localhost:8000"
    whatsapp_outbound_provider: str = "fake"
    meta_whatsapp_verify_token: str = ""
    meta_whatsapp_app_secret: str = ""
    meta_whatsapp_access_token: str = ""
    meta_whatsapp_phone_number_id: str = ""
    whatsapp_supplier_order_template: str = ""
    whatsapp_supplier_order_template_lang: str = "es"
    owner_wa_numbers: str = ""
    owner_dashboard_token: str = ""
    public_signup_enabled: bool = False
    public_signup_max_per_window: int = 5
    public_signup_window_s: int = 3600
    trusted_proxy_hops: int = 0
    enable_live_payments: bool = False
    qr_provider: str = "fake"
    whatsapp_debounce_s: float = DEFAULT_DEBOUNCE_S


class TurnIn(BaseModel):
    wa_number: str
    text: str
    tenant_id: str = Field(default=str(PILOT_TENANT_ID))


class ReplyIn(BaseModel):
    text: str


class ChatCloseIn(BaseModel):
    action: str = ""


class OrderStatusIn(BaseModel):
    status: str


class DeliveryIn(BaseModel):
    recipient_name: str
    address: str


class ManualItemIn(BaseModel):
    variant_sku: str = ""
    quantity: int = 1


class ManualOrderIn(BaseModel):
    wa_number: str = ""
    name: str | None = None
    address: str | None = None
    items: list[ManualItemIn] = Field(default_factory=list)
    recipient_name: str | None = None
    delivery_address: str | None = None


class OrderPatchIn(BaseModel):
    name: str | None = None
    address: str | None = None
    items: list[ManualItemIn] | None = None
    recipient_name: str | None = None
    delivery_address: str | None = None
    mark_cash_paid: bool = False


class OperatorRuleIn(BaseModel):
    when_event: str
    if_threshold: str
    then_action: str


class OperatorFlowTeamIn(BaseModel):
    employee_key: str
    module: str


class OperatorFlowMapPublishIn(BaseModel):
    kinds: list[str]
    team: list[OperatorFlowTeamIn] = []


class OperatorReviseIn(BaseModel):
    then_action: str


class OperatorRevertIn(BaseModel):
    version: int


class OperatorAutonomyIn(BaseModel):
    tenant_id: str
    action: str
    level: str


class OperatorEmployeePatchIn(BaseModel):
    tenant_id: str
    employee_key: str
    enabled: bool | None = None
    display_name: str | None = None
    style: str | None = None


class OperatorEmployeeCloneIn(BaseModel):
    tenant_id: str
    base_role: str
    display_name: str
    style: str = ""


class OperatorEmployeeArchiveIn(BaseModel):
    tenant_id: str
    employee_key: str


class OperatorProvisionIn(BaseModel):
    name: str
    industry: str


class OperatorConnectIn(BaseModel):
    source: str
    target: str
    port: str


class PublicSignupIn(BaseModel):
    name: str
    industry: str
    invite: str = ""


class CatalogIn(BaseModel):
    codigo: str
    name: str
    category: str = "general"
    price: str
    currency: str = "BOB"
    stock: int = 1
    tracks_stock: bool = True
    description: str = ""
    subcategory: str = ""
    brand: str = ""
    material: str = ""
    season: str = ""
    style: str = ""
    talla: str = ""
    color: str = ""
    codigo_referencia: str = ""
    image_url: str = ""


class CategorySortIn(BaseModel):
    name: str
    sort_order: int = 0


class CatalogPatchIn(BaseModel):
    """Partial product edit. Identity (product_sku, variant_sku, codigo) stays put."""

    name: str | None = None
    description: str | None = None
    category: str | None = None
    subcategory: str | None = None
    brand: str | None = None
    material: str | None = None
    season: str | None = None
    style: str | None = None
    talla: str | None = None
    color: str | None = None
    price: str | None = None
    currency: str | None = None
    stock: int | None = None
    codigo_referencia: str | None = None
    image_url: str | None = None


class ComboComponentIn(BaseModel):
    variant_sku: str
    quantity: int = 1


class ComboIn(BaseModel):
    codigo: str
    name: str
    price: str
    category: str = "Combos"
    currency: str = "BOB"
    components: list[ComboComponentIn]
    event_date: str = ""
    pin: str | None = None


class ComboPatchIn(BaseModel):
    name: str | None = None
    price: str | None = None
    category: str | None = None
    components: list[ComboComponentIn] | None = None
    event_date: str | None = None
    pin: str | None = None


class ModifierIn(BaseModel):
    name: str
    price_delta: str
    currency: str = "BOB"


class CatalogAvailabilityIn(BaseModel):
    available: bool
    stock: int | None = None


class NoteIn(BaseModel):
    body: str


class ReminderRunIn(BaseModel):
    send: bool = False


class ReminderPreviewIn(BaseModel):
    customer_id: str
    kind: str | None = None


class ReminderSendIn(BaseModel):
    customer_id: str
    kind: str
    confirm: bool = False


class PanelUserIn(BaseModel):
    name: str
    email: str
    role: str
    secret: str
    pin: str | None = None
    job_title: str | None = None


class PanelSecretResetIn(BaseModel):
    secret: str


class PanelLoginIn(BaseModel):
    email: str
    secret: str


class OwnerLoginIn(BaseModel):
    email: str
    secret: str


class OwnerWhatsappIn(BaseModel):
    phone_number_id: str
    access_token: str = ""


class OwnerAutonomyIn(BaseModel):
    action: str
    level: str


class OwnerEmployeePatchIn(BaseModel):
    employee_key: str
    enabled: bool | None = None
    display_name: str | None = None
    style: str | None = None


class OwnerEmployeeCloneIn(BaseModel):
    base_role: str
    display_name: str
    style: str = ""


class OwnerEmployeeArchiveIn(BaseModel):
    employee_key: str


class PanelActor:
    def __init__(self, role: str, name: str, user_id: UUID | None) -> None:
        self.role = role
        self.name = name
        self.user_id = user_id


class CashIn(BaseModel):
    direction: str
    amount: str
    reason: str = ""
    currency: str = "BOB"
    category: str = ""
    method: str = "cash"


class CashVoidIn(BaseModel):
    reason: str = ""
    pin: str | None = None


class CashSessionOpenIn(BaseModel):
    opening_float: str
    currency: str = "BOB"


class CashSessionCloseIn(BaseModel):
    counted_cash: str
    note: str = ""
    pin: str | None = None


class CashSessionReopenIn(BaseModel):
    pin: str | None = None


class AnalyticsThresholdsIn(BaseModel):
    qr_pending_hours: int | None = None
    inactive_days: int | None = None
    digest_whatsapp_enabled: bool | None = None


class AnalyticsDigestRunIn(BaseModel):
    force: bool = False
    dry_run: bool = False


def _masked_owner_destinations(numbers: list[str]) -> list[str]:
    masked: list[str] = []
    for number in numbers:
        digits = "".join(ch for ch in number if ch.isdigit())
        if len(digits) < 4:
            continue
        masked.append(f"•••{digits[-4:]}")
    return masked


def _thresholds_payload(
    thresholds: object, *, can_edit: bool, owner_numbers: list[str]
) -> dict[str, object]:
    from factory_os.domain.analytics_thresholds import AnalyticsThresholds

    if not isinstance(thresholds, AnalyticsThresholds):
        raise TypeError("thresholds")
    payload: dict[str, object] = dict(thresholds.to_public())
    payload["can_edit"] = can_edit
    if can_edit:
        payload["digest_destinations"] = _masked_owner_destinations(owner_numbers)
    return payload


def _analytics_digest_preview(store, tenant: UUID, *, now, force: bool) -> dict[str, object]:
    """Return the digest text without sending. Empty alerts stay no_alerts."""
    from datetime import datetime

    from factory_os.domain.analytics import build_analytics_summary
    from factory_os.domain.analytics_digest import format_analytics_digest

    if not isinstance(now, datetime):
        raise TypeError("digest_preview")
    thresholds = store.get_analytics_thresholds(tenant)
    if not thresholds.digest_whatsapp_enabled and not force:
        return {"status": "disabled", "sent": 0, "reason": "disabled", "text_preview": ""}
    summary = build_analytics_summary(store, tenant, period="7d", now=now)
    alerts = list(summary.get("alerts") or [])
    if not alerts:
        return {"status": "no_alerts", "sent": 0, "reason": "no_alerts", "text_preview": ""}
    text = format_analytics_digest(summary)
    return {
        "status": "preview",
        "sent": 0,
        "dry_run": True,
        "alert_type_count": len(alerts),
        "text_preview": text,
    }


class AnalyticsAskIn(BaseModel):
    question: str
    period: str | None = None


class CashSaleLineIn(BaseModel):
    variant_sku: str
    quantity: int = 1
    options: list[str] = Field(default_factory=list)


def _requested_sale_lines(lines: list[CashSaleLineIn]):
    from factory_os.domain.cash_sales import RequestedLine

    return [
        RequestedLine(item.variant_sku, int(item.quantity), tuple(item.options or []))
        for item in lines
    ]


class CashSaleIn(BaseModel):
    method: str = "cash"
    lines: list[CashSaleLineIn]
    discount_amount: str | None = None
    pin: str | None = None


class CashTabIn(BaseModel):
    table: str
    lines: list[CashSaleLineIn]


class CashTabChargeIn(BaseModel):
    method: str = "cash"
    discount_amount: str | None = None
    pin: str | None = None


class SupplierIn(BaseModel):
    name: str
    contact_name: str = ""
    phone: str = ""
    whatsapp: str = ""
    email: str = ""
    notes: str = ""
    payment_terms: str = "cash"
    lead_time_days: int = 0


class SupplierPatchIn(BaseModel):
    name: str | None = None
    contact_name: str | None = None
    phone: str | None = None
    whatsapp: str | None = None
    email: str | None = None
    notes: str | None = None
    payment_terms: str | None = None
    lead_time_days: int | None = None
    active: bool | None = None


class VariantSupplierIn(BaseModel):
    supplier_id: str | None = None


class ReorderThresholdIn(BaseModel):
    threshold: int


class StockReceiveIn(BaseModel):
    variant_sku: str
    quantity: int
    unit_cost: str | None = None
    currency: str = "BOB"
    payment_method: str = "cash"
    supplier_id: str | None = None
    received_at: str | None = None


class PurchaseOrderLineIn(BaseModel):
    variant_sku: str
    quantity: int
    unit_cost: str | None = None
    currency: str = "BOB"


class PurchaseOrderIn(BaseModel):
    supplier_id: str | None = None
    lines: list[PurchaseOrderLineIn] = Field(default_factory=list)
    notes: str = ""


class PurchaseOrderStatusIn(BaseModel):
    status: str


class PurchaseOrderReceiveLineIn(BaseModel):
    variant_sku: str
    quantity: int
    unit_cost: str | None = None
    currency: str = "BOB"


class PurchaseOrderReceiveIn(BaseModel):
    lines: list[PurchaseOrderReceiveLineIn] = Field(default_factory=list)
    payment_method: str = "cash"


class PurchaseOrderPaymentIn(BaseModel):
    amount: str
    method: str
    currency: str = "BOB"


class PurchaseOrderSendWhatsappIn(BaseModel):
    confirm: bool = False


class JournalPeriodIn(BaseModel):
    date_from: str = Field(alias="from")
    date_to: str = Field(alias="to")

    model_config = {"populate_by_name": True}


class JournalAdjustmentLineIn(BaseModel):
    account_code: str
    direction: str
    amount: str


class JournalAdjustmentIn(BaseModel):
    memo: str = ""
    lines: list[JournalAdjustmentLineIn]


class InvoiceIn(BaseModel):
    order_id: str


def _owner_numbers(settings: Settings) -> list[str]:
    return [part.strip() for part in settings.owner_wa_numbers.split(",") if part.strip()]


def _build_channel(settings: Settings) -> FakeChannel | MetaChannel:
    if (
        settings.whatsapp_outbound_provider == "meta"
        and settings.meta_whatsapp_access_token
        and settings.meta_whatsapp_phone_number_id
    ):
        return MetaChannel(
            settings.meta_whatsapp_access_token,
            settings.meta_whatsapp_phone_number_id,
        )
    return FakeChannel()


def _gateway(settings: Settings, trace_log=None):
    return build_gateway(
        GatewaySettings(
            model_provider=settings.model_provider,
            google_api_key=settings.google_api_key,
            gemini_default_model_id=settings.gemini_default_model_id,
            model_secondary_provider=settings.model_secondary_provider,
            openrouter_api_key=settings.openrouter_api_key,
            openrouter_model_id=settings.openrouter_model_id,
            groq_api_key=settings.groq_api_key,
            groq_model_id=settings.groq_model_id,
            model_timeout_s=settings.model_timeout_s,
        ),
        trace_log=trace_log,
    )


@lru_cache(maxsize=1)
def get_shop() -> ShopRuntime:
    from dotenv import load_dotenv

    from factory_os.harness.agent_trace import AgentTraceLog, postgres_trace_sink

    # Baneco factory reads os.environ; pydantic Settings alone does not export .env there.
    load_dotenv(Path(__file__).resolve().parents[4] / ".env", override=False)
    settings = Settings()
    local_mode = settings.app_env.strip().lower() in {"local", "test"}
    pilot_runtime = (
        settings.catalog_seed.strip().lower() in {"closet", "cafe"}
        and settings.app_env.strip().lower() != "test"
    )
    migration_db_url = settings.database_url.strip()
    runtime_db_url = settings.database_runtime_url.strip()
    if pilot_runtime and not migration_db_url:
        raise RuntimeError("database_url_required_for_closet_pilot")
    if migration_db_url:
        if not runtime_db_url or runtime_db_url == migration_db_url:
            raise RuntimeError("separate_database_runtime_url_required")
        from factory_os.domain.postgres import (
            assert_rls_runtime_role,
            ensure_local_rls_runtime_role,
            local_database_host_allowed,
        )

        if local_mode and not (
            local_database_host_allowed(migration_db_url)
            and local_database_host_allowed(runtime_db_url)
        ):
            raise RuntimeError("local_remote_database_refused")
        if local_mode:
            ensure_local_rls_runtime_role(migration_db_url, runtime_db_url)
        else:
            assert_rls_runtime_role(runtime_db_url)
    elif not local_mode:
        raise RuntimeError("database_url_required_outside_local")
    elif runtime_db_url:
        raise RuntimeError("database_url_admin_required_for_runtime_database")
    # Schema changes and seed use the admin URL; application reads/writes use
    # only the separately configured RLS-constrained role.
    db_url = runtime_db_url
    channel = _build_channel(settings)
    if pilot_runtime and not isinstance(channel, MetaChannel):
        raise RuntimeError("meta_whatsapp_provider_required_for_closet_pilot")
    inbox = f"{settings.public_base_url.rstrip('/')}/inbox"
    seed = catalog_seed_path(settings.catalog_seed)
    extras = extra_seed_paths(settings.catalog_seed)
    sink = postgres_trace_sink(db_url) if db_url else None
    trace_log = AgentTraceLog(sink=sink)
    gateway = _gateway(settings, trace_log=trace_log)
    if pilot_runtime:
        from factory_os.harness.model_gateway import FakeGateway

        if isinstance(gateway, FakeGateway):
            raise RuntimeError("live_model_provider_required_for_closet_pilot")
    from factory_os.tools.payments import build_payment_provider

    payments = build_payment_provider()
    if (not local_mode or pilot_runtime) and payments.name != "baneco":
        raise RuntimeError("baneco_payment_provider_required_for_closet_pilot")
    from factory_os.tools.agentos_settlement import notifier_from_env

    settlement_notifier = notifier_from_env()
    if db_url:
        # Production migrates. It does not load the seed or delete SKUs missing
        # from that file. Prune stays on the local/test pilot (ADR-017).
        sync_seed = local_mode
        store = open_postgres_shop(
            migration_db_url or db_url,
            PILOT_TENANT_ID,
            seed if sync_seed else None,
            extra_paths=extras if sync_seed else None,
            runtime_url=db_url,
            sync_seed=sync_seed,
        )
        if sync_seed:
            from factory_os.domain.postgres import retain_catalog_skus

            loaded = [
                json.loads(path.read_text(encoding="utf-8"))["products"]
                for path in [seed, *extras]
            ]
            keep = {str(row["sku"]) for products in loaded for row in products if row.get("sku")}
            keep_variants = {
                str(row["variant_sku"])
                for products in loaded
                for row in products
                if row.get("variant_sku")
            }
            retain_catalog_skus(db_url, PILOT_TENANT_ID, keep, keep_variants)
        return ShopRuntime(
            store,
            payments=payments,
            channel=channel,
            owner_numbers=_owner_numbers(settings),
            inbox_base_url=inbox,
            gateway=gateway,
            database_url=db_url or None,
            settlement_notifier=settlement_notifier,
        )
    store = MemoryCommerceStore(PILOT_TENANT_ID)
    load_catalog_json(seed, store)
    for extra in extras:
        load_catalog_json(extra, store)
    return ShopRuntime(
        store,
        payments=payments,
        channel=channel,
        owner_numbers=_owner_numbers(settings),
        inbox_base_url=inbox,
        gateway=gateway,
        database_url=db_url or None,
        settlement_notifier=settlement_notifier,
    )


def _valid_meta_signature(secret: str, payload: bytes, header: str) -> bool:
    if not secret:
        return False
    if not header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(header[7:], expected)


def _cart_view(cart: list) -> dict[str, object] | None:
    from factory_os.domain.cart_quote import quote_lines

    if not cart:
        return None
    quote = quote_lines(cart)
    return quote.as_dict()


def _blank(value: object) -> bool:
    return not str(value or "").strip()


def _orders_newest_first(orders: list) -> list:
    """Most recent delivery source: created_at when the store has it, else list order."""

    def key(pair: tuple[int, object]) -> tuple:
        index, order = pair
        created = getattr(order, "created_at", None)
        if created is None:
            return (0, index)
        return (1, created, index)

    ranked = sorted(enumerate(orders), key=key, reverse=True)
    return [order for _, order in ranked]


def _hydrate_customer_from_latest_delivery(store, tenant: UUID, customer: Customer) -> Customer:
    """Fill only empty name/address from the latest delivery. Never invent a WhatsApp profile name."""
    if not _blank(customer.name) and not _blank(customer.address):
        return customer
    own = [order for order in store.list_orders(tenant) if order.customer_id == customer.id]
    chosen = None
    for order in _orders_newest_first(own):
        delivery = store.delivery_for_order(tenant, order.id)
        if delivery is None:
            continue
        if not _blank(delivery.recipient_name) or not _blank(delivery.address):
            chosen = delivery
            break
    if chosen is None:
        return customer
    name = chosen.recipient_name.strip() if _blank(customer.name) and not _blank(chosen.recipient_name) else None
    address = chosen.address.strip() if _blank(customer.address) and not _blank(chosen.address) else None
    if name is None and address is None:
        return customer
    store.update_customer(tenant, customer.wa_number, name, address)
    refreshed = store.get_customer(tenant, customer.id)
    return refreshed if refreshed is not None else customer


def _order_item_media(store, tenant: UUID, variant_sku: str) -> dict[str, str]:
    from factory_os.domain.media import primary_media_fields

    record = store.get_variant(tenant, variant_sku) if hasattr(store, "get_variant") else None
    if record is None:
        return {"media_id": "", "thumb_url": "", "image_url": ""}
    media_id, thumb_url = primary_media_fields(
        store, tenant, record.product_sku, attrs=dict(record.attributes or {})
    )
    return {
        "media_id": media_id,
        "thumb_url": thumb_url,
        "image_url": str(record.attributes.get("image_url") or ""),
    }


def _order_row(store, tenant: UUID, order) -> dict[str, object]:
    from factory_os.domain.cart_quote import charge_total

    payment = store.payment_for_order(tenant, order.id)
    customer = store.get_customer(tenant, order.customer_id)
    delivery = store.delivery_for_order(tenant, order.id)
    location = None
    if delivery is not None and delivery.address.strip():
        location = delivery.address.strip()
    elif customer is not None and (customer.address or "").strip():
        location = customer.address.strip()
    return {
        "id": str(order.id),
        "public_number": order.public_number,
        "customer_id": str(order.customer_id),
        "customer_name": customer.name if customer else None,
        "customer_address": (customer.address or "").strip() if customer else "",
        "wa_number": customer.wa_number if customer else "",
        "location": location,
        "status": order.status,
        "delivered_at": order.delivered_at.isoformat() if order.delivered_at else None,
        "delivered_by": order.delivered_by,
        "items": [
            {
                "variant_sku": item.variant_sku,
                "name": item.name,
                "quantity": item.quantity,
                "unit_price": str(item.unit_price),
                "currency": item.currency,
                **_order_item_media(store, tenant, item.variant_sku),
            }
            for item in order.items
        ],
        "payment_status": payment.status.value if payment else None,
        "provider": payment.provider if payment else None,
        "provider_ref": payment.provider_ref if payment else None,
        "discount": str(order.discount_amount),
        "hold_minutes": order.hold_minutes,
        "total": str(charge_total(order.items, order.discount_amount)),
        "fulfill_on": order.fulfill_on.isoformat() if getattr(order, "fulfill_on", None) else None,
        "has_delivery": delivery is not None,
        "delivery": (
            None
            if delivery is None
            else {
                "address": delivery.address,
                "recipient_name": delivery.recipient_name,
            }
        ),
    }


def _manual_lines(items: list[ManualItemIn]):
    from factory_os.domain.owner_orders import ManualLine

    return [ManualLine(item.variant_sku, item.quantity) for item in items]


def _customer_order_view(store, tenant: UUID, order) -> dict[str, object]:
    from factory_os.domain.cart_quote import charge_total

    payment = store.payment_for_order(tenant, order.id)
    delivery = store.delivery_for_order(tenant, order.id)
    currency = "BOB"
    if order.items:
        currency = str(order.items[0].currency or "BOB").strip() or "BOB"
    delivered = order.delivered_at
    return {
        "id": str(order.id),
        "public_number": order.public_number,
        "status": order.status,
        "items": [
            {"name": item.name, "quantity": item.quantity, "unit_price": str(item.unit_price)}
            for item in order.items
        ],
        "payment_status": payment.status.value if payment else None,
        "provider_ref": payment.provider_ref if payment else None,
        "discount": str(order.discount_amount),
        "total": str(charge_total(order.items, order.discount_amount)),
        "currency": currency,
        "delivered_at": delivered.isoformat() if delivered else None,
        "delivery": (
            {"address": delivery.address, "recipient_name": delivery.recipient_name}
            if delivery is not None
            else None
        ),
    }


def _chat_has_products(shop: ShopRuntime, conversation: Conversation) -> bool:
    from factory_os.domain.chat_close import chat_has_products

    return chat_has_products(shop.store, conversation)


def _chat_has_qr(shop: ShopRuntime, conversation: Conversation) -> bool:
    from factory_os.domain.chat_close import chat_has_qr

    return chat_has_qr(shop.store, conversation)


def _summary(shop: ShopRuntime, conversation: Conversation) -> dict[str, object]:
    customer = shop.store.get_customer(conversation.tenant_id, conversation.customer_id)
    last = conversation.messages[-1][1] if conversation.messages else ""
    return {
        "id": str(conversation.id),
        "wa_number": customer.wa_number if customer else "",
        "name": customer.name if customer else None,
        "address": customer.address if customer else None,
        "last_text": last,
        "needs_human": conversation.state.needs_human,
        "human_takeover": conversation.state.human_takeover,
        "message_count": len(conversation.messages),
        "cart": _cart_view(conversation.state.cart),
        "has_products": _chat_has_products(shop, conversation),
        "has_qr": _chat_has_qr(shop, conversation),
        "chat_resolution": conversation.state.chat_resolution,
        "outcome": conversation.outcome,
    }


def _conversation_files(shop: ShopRuntime, conversation: Conversation) -> list[dict[str, object]]:
    from factory_os.domain.chat_media import media_view

    list_fn = getattr(shop.store, "list_conversation_media", None)
    if not callable(list_fn):
        return []
    rows = list_fn(conversation.tenant_id, conversation.id)
    out: list[dict[str, object]] = []
    for link in rows:
        asset = None
        if link.asset_id is not None:
            asset = shop.store.get_media_asset(conversation.tenant_id, link.asset_id)
        out.append(media_view(link, asset))
    return out


def _detail(shop: ShopRuntime, conversation: Conversation) -> dict[str, object]:
    customer = shop.store.get_customer(conversation.tenant_id, conversation.customer_id)
    files = _conversation_files(shop, conversation)
    by_index: dict[int, dict[str, object]] = {}
    for item in files:
        idx = item.get("message_index")
        if isinstance(idx, int) and idx not in by_index:
            by_index[idx] = item
    messages: list[dict[str, object]] = []
    for index, (role, body) in enumerate(conversation.messages):
        row: dict[str, object] = {"role": role, "text": body}
        media = by_index.get(index)
        if media is not None:
            row["media"] = {
                "asset_id": media.get("asset_id"),
                "kind": media.get("kind"),
                "mime": media.get("mime"),
                "filename": media.get("filename"),
                "size_bytes": media.get("size_bytes"),
                "thumb_url": media.get("thumb_url"),
                "status": media.get("status"),
                "origin": media.get("origin"),
            }
        messages.append(row)
    return {
        **_summary(shop, conversation),
        "messages": messages,
        "files": files,
        "customer": {
            "wa_number": customer.wa_number if customer else "",
            "name": customer.name if customer else None,
            "address": customer.address if customer else None,
        },
    }


def _disposition_param(header: str, key: str) -> str | None:
    quoted = re.search(rf"{key}\s*=\s*\"([^\"]*)\"", header, re.IGNORECASE)
    if quoted is not None:
        return quoted.group(1)
    bare = re.search(rf"{key}\s*=\s*([^;]+)", header, re.IGNORECASE)
    if bare is None:
        return None
    return bare.group(1).strip()


def _multipart_fields(body: bytes, content_type: str) -> list[tuple[str, str | None, str, bytes]]:
    marker = content_type.lower().find("boundary=")
    if marker < 0:
        raise ValueError("bad_body")
    token = content_type[marker + len("boundary=") :].strip()
    if ";" in token:
        token = token.split(";", 1)[0].strip()
    boundary = b"--" + token.strip('"').encode("utf-8", "replace")
    fields: list[tuple[str, str | None, str, bytes]] = []
    for piece in body.split(boundary):
        chunk = piece
        if chunk.startswith(b"\r\n"):
            chunk = chunk[2:]
        elif chunk.startswith(b"\n"):
            chunk = chunk[1:]
        if chunk.endswith(b"\r\n"):
            chunk = chunk[:-2]
        elif chunk.endswith(b"\n"):
            chunk = chunk[:-1]
        if chunk.endswith(b"--"):
            chunk = chunk[:-2].rstrip(b"\r\n")
        if not chunk or chunk in (b"--",):
            continue
        separator = b"\r\n\r\n" if b"\r\n\r\n" in chunk else b"\n\n"
        if separator not in chunk:
            continue
        head, data = chunk.split(separator, 1)
        headers: dict[str, str] = {}
        for line in head.decode("utf-8", "replace").splitlines():
            if ":" not in line:
                continue
            name, value = line.split(":", 1)
            headers[name.strip().lower()] = value.strip()
        disposition = headers.get("content-disposition", "")
        field_name = _disposition_param(disposition, "name")
        if not field_name:
            continue
        fields.append(
            (
                field_name,
                _disposition_param(disposition, "filename"),
                headers.get("content-type", ""),
                data,
            )
        )
    return fields


async def _propose_inputs(request: Request) -> tuple[str | None, str | None, str]:
    from factory_os.domain.knowledge_ingest import text_from_upload

    content_type = request.headers.get("content-type", "")
    media = content_type.split(";", 1)[0].strip().lower()
    if media.startswith("multipart/"):
        try:
            fields = _multipart_fields(await request.body(), content_type)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="bad_body") from exc
        filename: str | None = None
        kind: str | None = None
        upload: tuple[str | None, str, bytes] | None = None
        for name, upload_name, part_type, data in fields:
            if name == "kind" and upload_name is None:
                kind = data.decode("utf-8", "replace").strip() or None
            elif name == "file" and upload is None:
                upload = (upload_name, part_type, data)
                filename = upload_name
        if upload is None:
            raise HTTPException(status_code=400, detail="bad_body")
        upload_name, part_type, data = upload
        try:
            text = text_from_upload(upload_name, data, content_type=part_type)
        except ValueError as exc:
            if str(exc) == "unsupported_document":
                raise HTTPException(status_code=400, detail="unsupported_document") from exc
            raise HTTPException(status_code=400, detail="bad_body") from exc
        return filename, kind, text

    try:
        payload = await request.json()
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="bad_body") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("text"), str):
        raise HTTPException(status_code=400, detail="bad_body")
    filename = payload.get("filename")
    kind = payload.get("kind")
    text = payload["text"]
    if isinstance(filename, str) and filename.strip():
        try:
            text = text_from_upload(filename.strip(), text.encode("utf-8"), content_type="text/plain")
        except ValueError as exc:
            if str(exc) == "unsupported_document":
                raise HTTPException(status_code=400, detail="unsupported_document") from exc
            raise HTTPException(status_code=400, detail="bad_body") from exc
        return filename.strip(), kind if isinstance(kind, str) and kind.strip() else None, text
    return None, kind if isinstance(kind, str) and kind.strip() else None, text


_CATALOG_SEARCH_FIELDS = (
    "name",
    "description",
    "category",
    "subcategory",
    "brand",
    "material",
    "codigo",
    "color",
    "talla",
    "variant_sku",
    "product_sku",
    "style",
    "season",
)

_CATALOG_ATTR_FIELDS = (
    "subcategory",
    "brand",
    "material",
    "season",
    "style",
    "talla",
    "color",
    "codigo_referencia",
    "image_url",
)


def _catalog_row(
    record: VariantRecord,
    sold_units: int,
    *,
    store=None,
    tenant: UUID | None = None,
) -> dict[str, object]:
    attrs = record.attributes
    units = int(sold_units)
    disabled = bool(attrs.get("disabled"))
    media_id = ""
    thumb_url = ""
    if store is not None and tenant is not None:
        from factory_os.domain.media import primary_media_fields

        media_id, thumb_url = primary_media_fields(
            store, tenant, record.product_sku, attrs=dict(attrs or {})
        )
    return {
        "product_sku": record.product_sku,
        "variant_sku": record.variant_sku,
        "name": record.name,
        "description": record.description,
        "category": record.category,
        "subcategory": str(attrs.get("subcategory") or ""),
        "brand": str(attrs.get("brand") or ""),
        "material": str(attrs.get("material") or ""),
        "season": str(attrs.get("season") or ""),
        "style": str(attrs.get("style") or ""),
        "talla": str(attrs.get("talla") or ""),
        "color": str(attrs.get("color") or ""),
        "codigo_referencia": str(attrs.get("codigo_referencia") or ""),
        "image_url": str(attrs.get("image_url") or ""),
        "image_path": str(attrs.get("image_path") or ""),
        "thumb_path": str(attrs.get("thumb_path") or ""),
        "media_id": media_id,
        "thumb_url": thumb_url,
        "price": str(record.price),
        "currency": record.currency,
        "stock": record.stock,
        "tracks_stock": attrs.get("tracks_stock", True) is not False
        and str(attrs.get("tracks_stock", True)).strip().lower()
        not in {"0", "false", "no"},
        "codigo": str(attrs.get("codigo") or ""),
        "test_only": bool(attrs.get("test_only")),
        "available": not disabled,
        "sold_units": units,
        "sold": units > 0,
        "supplier_id": str(record.supplier_id) if record.supplier_id else None,
        "reorder_threshold": int(record.reorder_threshold),
    }


def _catalog_matches(row: dict[str, object], needle: str) -> bool:
    return any(needle in str(row.get(key) or "").casefold() for key in _CATALOG_SEARCH_FIELDS)


def _parse_catalog_price(raw: str) -> Decimal:
    try:
        price = Decimal(raw.strip().replace(",", "."))
    except (InvalidOperation, AttributeError) as exc:
        raise HTTPException(status_code=400, detail="bad_price") from exc
    if price < 0:
        raise HTTPException(status_code=400, detail="bad_price")
    return price


def _report_name_parts(report_name: str) -> tuple[str, str | None]:
    """Split ``orders.csv`` into ``("orders", "csv")``. A bare name has no suffix."""
    name = report_name.strip()
    for ext in (".csv", ".xlsx"):
        if name.lower().endswith(ext):
            return name[: -len(ext)].lower(), ext[1:]
    return name.lower(), None


def create_app(
    shop: ShopRuntime | None = None,
    settings: Settings | None = None,
    deduper: InboundDeduper | None = None,
    inbound_buffer: InboundBuffer | None = None,
    media_downloader=None,
    media_enricher=None,
) -> FastAPI:
    cfg = settings or Settings()
    claimer = deduper or build_inbound_deduper(
        redis_url=cfg.redis_url,
        database_url=cfg.database_url,
        memory=MemoryInboundDeduper() if shop is not None else None,
    )
    buffer = inbound_buffer or build_inbound_buffer(
        redis_url=cfg.redis_url if shop is None else "",
        memory=MemoryInboundBuffer() if shop is not None else None,
    )
    debounce_s = 0.0 if shop is not None else float(cfg.whatsapp_debounce_s)
    if media_downloader is None and cfg.meta_whatsapp_access_token.strip():
        from factory_os.tools.whatsapp_media import download_meta_media

        media_downloader = download_meta_media
    if media_enricher is None:
        from factory_os.domain.media_enrichment import FakeMediaEnricher

        media_enricher = FakeMediaEnricher()
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _lifespan(_app: FastAPI):
        stop = asyncio.Event()

        async def _release_holds() -> None:
            from factory_os.domain.order_hold import release_expired_unpaid_orders

            while not stop.is_set():
                try:
                    release_expired_unpaid_orders(runtime().store, tenant_id())
                except Exception:
                    pass
                try:
                    await asyncio.wait_for(stop.wait(), timeout=30)
                except TimeoutError:
                    continue

        task = asyncio.create_task(_release_holds())
        try:
            yield
        finally:
            stop.set()
            task.cancel()

    app = FastAPI(title="Factory Agent OS", version="0.1.0", lifespan=_lifespan)

    class AuditedRoute(APIRoute):
        def get_route_handler(self):  # type: ignore[override]
            original = super().get_route_handler()

            async def audited(request: Request) -> Response:
                response = await original(request)
                actor = getattr(request.state, "panel_actor", None)
                if (
                    actor is not None
                    and request.method in {"POST", "PUT", "PATCH", "DELETE"}
                    and response.status_code < 400
                    and request.url.path.startswith("/api/")
                ):
                    runtime().store.add_human_audit(
                        tenant_id(),
                        actor.user_id,
                        actor.name,
                        actor.role,
                        request.method,
                        request.url.path,
                    )
                return response

            return audited

    app.router.route_class = AuditedRoute
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[cfg.frontend_origin, cfg.public_base_url],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def runtime() -> ShopRuntime:
        return shop if shop is not None else get_shop()

    def tenant_id() -> UUID:
        return runtime().store.tenant_id

    def _database_url() -> str | None:
        return (cfg.database_runtime_url or "").strip() or None

    @app.middleware("http")
    async def enforce_enabled_modules(request: Request, call_next):  # type: ignore[no-untyped-def]
        from factory_os.domain.modules import module_for_api_path, module_is_enabled

        module = module_for_api_path(request.url.path)
        if module is not None and not module_is_enabled(
            tenant_id(), module, url=_database_url()
        ):
            from fastapi.responses import JSONResponse

            return JSONResponse({"detail": "module_disabled"}, status_code=404)
        return await call_next(request)

    def _process_whatsapp_inbound(
        wa_number: str,
        text: str,
        message_id: str | None = None,
        *,
        media_id: str | None = None,
        media_kind: str | None = None,
        mime: str | None = None,
        filename: str | None = None,
        caption: str | None = None,
    ) -> None:
        try:
            joined = buffer.coalesce(
                wa_number,
                text,
                debounce_s=debounce_s,
                tenant_id=str(tenant_id()),
            )
            if joined is None:
                return
            channel = runtime().channel
            notify = getattr(channel, "notify_typing", None)
            if callable(notify):
                notify(wa_number, message_id)
            shop_rt = runtime()
            tid = tenant_id()
            shop_rt.handle_inbound(tid, wa_number, joined)
            if media_id and media_kind:
                try:
                    customer = shop_rt.store.get_or_create_customer(tid, wa_number)
                    conv = shop_rt.store.get_or_create_conversation(tid, customer)
                    msg_index = max(0, len(conv.messages) - 1)
                    from factory_os.domain.chat_media import store_inbound_chat_media

                    store_inbound_chat_media(
                        shop_rt.store,
                        tid,
                        conversation_id=conv.id,
                        provider_ref=message_id,
                        media_id=media_id,
                        media_kind=media_kind,
                        mime=mime,
                        filename=filename,
                        caption=caption,
                        text_for_origin=text,
                        message_index=msg_index,
                        downloader=media_downloader,
                        access_token=cfg.meta_whatsapp_access_token,
                    )
                except Exception:
                    import logging

                    logging.getLogger("factory_os.api").exception(
                        "whatsapp media store failed wa=%s", wa_number
                    )
        except Exception:
            import logging

            logging.getLogger("factory_os.api").exception(
                "whatsapp inbound failed wa=%s", wa_number
            )

    def require_human(request: Request) -> PanelActor:
        token = (cfg.owner_dashboard_token or "").strip()
        if not token:
            raise HTTPException(status_code=503, detail="owner_auth_not_configured")
        auth = request.headers.get("authorization") or ""
        if not auth.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="owner_token_required")
        secret = auth.removeprefix("Bearer ").strip()
        if not secret:
            raise HTTPException(status_code=401, detail="owner_token_required")
        store = runtime().store
        tenant = tenant_id()
        if secret == token:
            header = (request.headers.get("x-panel-actor") or "").strip()
            if header and header != "bootstrap":
                try:
                    user_id = UUID(header)
                except ValueError as exc:
                    raise HTTPException(status_code=401, detail="owner_token_required") from exc
                user = store.get_panel_user(tenant, user_id)
                if user is None or not user.active:
                    raise HTTPException(status_code=401, detail="owner_token_required")
                actor = PanelActor(user.role, user.name, user.id)
            else:
                actor = PanelActor("owner", "Dueño", None)
        else:
            from factory_os.domain.panel_access import secret_matches

            user = next(
                (
                    item
                    for item in store.list_panel_users(tenant)
                    if item.active and secret_matches(secret, item.secret_salt, item.secret_hash)
                ),
                None,
            )
            if user is None:
                raise HTTPException(status_code=401, detail="owner_token_required")
            actor = PanelActor(user.role, user.name, user.id)
        request.state.panel_actor = actor
        return actor

    def require_owner(request: Request) -> PanelActor:
        from factory_os.domain.panel_access import is_owner_role

        actor = require_human(request)
        if not is_owner_role(actor.role):
            raise HTTPException(status_code=403, detail="panel_forbidden")
        return actor

    def require_supervisor(request: Request) -> PanelActor:
        from factory_os.domain.panel_access import is_supervisor_role

        actor = require_human(request)
        if not is_supervisor_role(actor.role):
            raise HTTPException(status_code=403, detail="panel_forbidden")
        return actor

    # In-process PIN failure counters (T4). Keyed by panel user id.
    _pin_failures: dict[str, int] = {}

    def _require_pin_if_configured(
        actor: PanelActor,
        pin: str | None,
        *,
        tenant: UUID,
    ) -> None:
        """Supervisor/owner PIN gate. Bootstrap owner (no user_id) skips PIN."""
        from factory_os.domain.panel_access import pin_matches

        if actor.user_id is None:
            return
        user = runtime().store.get_panel_user(tenant, actor.user_id)
        if user is None or not user.pin_hash or not user.pin_salt:
            return
        key = str(actor.user_id)
        if _pin_failures.get(key, 0) >= 3:
            raise HTTPException(status_code=403, detail="pin_locked")
        supplied = (pin or "").strip()
        if not supplied:
            raise HTTPException(status_code=400, detail="pin_required")
        if not pin_matches(supplied, user.pin_salt, user.pin_hash):
            _pin_failures[key] = _pin_failures.get(key, 0) + 1
            raise HTTPException(status_code=403, detail="bad_pin")
        _pin_failures[key] = 0

    def _sale_actor(request: Request, discount_amount: str | None, pin: str | None) -> PanelActor:
        """A discount needs the supervisor PIN. A sale without one stays a cashier sale."""
        raw = (discount_amount or "").strip().replace(",", ".")
        wants_discount = False
        if raw:
            try:
                wants_discount = Decimal(raw) > 0
            except (InvalidOperation, ValueError):
                wants_discount = True
        if wants_discount:
            actor = require_supervisor(request)
            _require_pin_if_configured(actor, pin, tenant=tenant_id())
            return actor
        return require_human(request)

    def _public_panel_user(user: object) -> dict[str, str]:
        from factory_os.domain.models import PanelUser

        if not isinstance(user, PanelUser):
            raise TypeError("panel user")
        return {
            "id": str(user.id),
            "name": user.name,
            "email": user.email,
            "role": user.role,
            "job_title": user.job_title,
        }

    @app.post("/api/panel/login")
    def panel_login(body: PanelLoginIn) -> dict[str, str]:
        from factory_os.domain.panel_access import secret_matches

        email = body.email.strip().lower()
        user = next(
            (
                item
                for item in runtime().store.list_panel_users(tenant_id())
                if item.active
                and item.email == email
                and secret_matches(body.secret, item.secret_salt, item.secret_hash)
            ),
            None,
        )
        if user is None:
            raise HTTPException(status_code=401, detail="owner_token_required")
        return {"actor_id": str(user.id), "name": user.name, "role": user.role}

    @app.post("/api/owner/login")
    def owner_login(body: OwnerLoginIn) -> dict[str, str]:
        from factory_os.domain.business_owners import open_owner_session

        opened = open_owner_session(
            body.email,
            body.secret,
            url=(cfg.database_runtime_url or "").strip() or None,
        )
        if opened is None:
            raise HTTPException(status_code=401, detail="owner_token_required")
        token, owner_tenant = opened
        return {"session": token, "tenant_id": str(owner_tenant)}

    def _owner_session(request: Request):
        from factory_os.domain.business_owners import owner_for_session

        auth = request.headers.get("authorization") or ""
        if not auth.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="owner_token_required")
        owner = owner_for_session(
            auth.removeprefix("Bearer ").strip(),
            url=(cfg.database_runtime_url or "").strip() or None,
        )
        if owner is None:
            raise HTTPException(status_code=401, detail="owner_token_required")
        return owner

    @app.delete("/api/owner/session")
    def owner_logout(request: Request) -> dict[str, bool]:
        from factory_os.domain.business_owners import close_owner_session

        auth = request.headers.get("authorization") or ""
        if not auth.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="owner_token_required")
        close_owner_session(
            auth.removeprefix("Bearer ").strip(),
            url=(cfg.database_runtime_url or "").strip() or None,
        )
        return {"ok": True}

    @app.get("/api/owner/business")
    def owner_business(request: Request) -> dict[str, object]:
        from factory_os.domain.operator_registry import (
            business_as_dict,
            list_businesses,
            load_business_channels,
            phone_for_tenant,
            token_is_set,
            whatsapp_status_for,
        )

        owner = _owner_session(request)
        load_business_channels((cfg.database_runtime_url or "").strip() or None)
        record = next(
            (
                item
                for item in list_businesses(url=(cfg.database_runtime_url or "").strip() or None)
                if item.tenant_id == owner.tenant_id
            ),
            None,
        )
        if record is None:
            raise HTTPException(status_code=404, detail="business_not_found")
        channel_url = (cfg.database_runtime_url or "").strip() or None
        payload = business_as_dict(record, url=channel_url)
        payload["whatsapp_phone_id"] = phone_for_tenant(owner.tenant_id)
        payload["whatsapp_status"] = whatsapp_status_for(
            owner.tenant_id,
            live_tenant_id=runtime().store.tenant_id,
            channel_configured=bool(
                cfg.meta_whatsapp_access_token.strip() and cfg.meta_whatsapp_phone_number_id.strip()
            ),
        )
        payload["whatsapp_token_set"] = token_is_set(owner.tenant_id)
        return payload

    @app.post("/api/owner/whatsapp")
    def owner_whatsapp(body: OwnerWhatsappIn, request: Request) -> dict[str, object]:
        from factory_os.domain.operator_registry import (
            accepted_business_token,
            assign_business_phone,
            keep_business_token,
            token_is_set,
            whatsapp_status_for,
        )

        owner = _owner_session(request)
        channel_url = (cfg.database_runtime_url or "").strip() or None
        try:
            token = accepted_business_token(
                body.access_token,
                reserved_token=cfg.meta_whatsapp_access_token,
            )
            phone = assign_business_phone(
                owner.tenant_id,
                body.phone_number_id,
                reserved_phone_id=cfg.meta_whatsapp_phone_number_id,
                url=channel_url,
            )
            keep_business_token(owner.tenant_id, token, url=channel_url)
        except ValueError as exc:
            code = str(exc)
            status = 409 if code in {"pilot_phone_reserved", "pilot_token_reserved", "phone_taken"} else 400
            raise HTTPException(status_code=status, detail=code) from exc
        return {
            "whatsapp_phone_id": phone,
            "whatsapp_status": whatsapp_status_for(
                owner.tenant_id,
                live_tenant_id=runtime().store.tenant_id,
                channel_configured=bool(
                    cfg.meta_whatsapp_access_token.strip()
                    and cfg.meta_whatsapp_phone_number_id.strip()
                ),
            ),
            "whatsapp_token_set": token_is_set(owner.tenant_id),
        }

    @app.get("/api/owner/messages")
    def owner_messages(request: Request) -> dict[str, object]:
        from factory_os.agents.reserved_shop import reserved_messages

        owner = _owner_session(request)
        return {
            "messages": reserved_messages(
                owner.tenant_id,
                url=(cfg.database_runtime_url or "").strip() or None,
            )
        }

    @app.post("/api/owner/autonomy")
    def owner_set_autonomy(request: Request, body: OwnerAutonomyIn) -> dict[str, object]:
        """Tighten autonomy for the signed-in business only. Cannot loosen the floor."""
        from factory_os.domain.autonomy import set_tenant_autonomy
        from factory_os.domain.operator_registry import list_businesses

        owner = _owner_session(request)
        channel_url = (cfg.database_runtime_url or "").strip() or None
        record = next(
            (
                item
                for item in list_businesses(url=channel_url)
                if item.tenant_id == owner.tenant_id
            ),
            None,
        )
        if record is None:
            raise HTTPException(status_code=404, detail="business_not_found")
        try:
            grants = set_tenant_autonomy(
                owner.tenant_id,
                industry=record.industry,
                action=body.action,
                level=body.level,
                url=channel_url,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "tenant_id": str(owner.tenant_id),
            "autonomy": [{"action": item.action, "level": item.level} for item in grants],
        }

    @app.get("/api/panel/users")
    def get_panel_users(request: Request) -> dict[str, object]:
        actor = require_owner(request)
        users = runtime().store.list_panel_users(tenant_id())
        if actor.role == "owner":
            users = [user for user in users if user.role != "admin"]
        return {"users": [_public_panel_user(user) for user in users]}

    @app.post("/api/operator/invites")
    def operator_issue_invite(request: Request) -> dict[str, str]:
        """Mint a one-time public signup code. Does not turn signup on."""
        require_human(request)
        from factory_os.domain.signup_invites import issue_invite

        return {"code": issue_invite(url=(cfg.database_runtime_url or "").strip() or None)}

    @app.post("/api/public/signup")
    def public_signup(body: PublicSignupIn, request: Request) -> dict[str, object]:
        """Self-service signup. Off unless the flag is on and the invite is unused."""
        if not cfg.public_signup_enabled:
            raise HTTPException(status_code=403, detail="signup_disabled")
        from factory_os.domain.operator_registry import business_as_dict, list_businesses
        from factory_os.domain.provision import TEMPLATE_MODULES, provision_business
        from factory_os.domain.signup_invites import consume_invite
        from factory_os.domain.signup_rate_limit import (
            record_signup,
            signup_client_ip,
            signup_slot_open,
        )

        peer = signup_client_ip(
            request.client.host if request.client is not None else "",
            request.headers.get("x-forwarded-for"),
            trusted_hops=cfg.trusted_proxy_hops,
        )
        channel_url = (cfg.database_runtime_url or "").strip() or None
        if not signup_slot_open(
            peer,
            limit=cfg.public_signup_max_per_window,
            window_s=float(cfg.public_signup_window_s),
            url=channel_url,
        ):
            raise HTTPException(status_code=429, detail="signup_rate_limited")
        industry = (body.industry or "").strip().lower()
        if industry not in TEMPLATE_MODULES:
            raise HTTPException(status_code=400, detail=f"unknown_industry:{body.industry}")
        if not consume_invite(
            body.invite,
            url=channel_url,
        ):
            raise HTTPException(status_code=403, detail="invite_required")
        try:
            tid = provision_business(
                name=body.name,
                industry=industry,
                url=channel_url,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        record_signup(peer, url=channel_url)
        record = next(
            item
            for item in list_businesses(url=(cfg.database_runtime_url or "").strip() or None)
            if item.tenant_id == tid
        )
        from factory_os.domain.business_owners import issue_business_owner

        email, secret = issue_business_owner(
            tid,
            name=body.name,
            url=(cfg.database_runtime_url or "").strip() or None,
        )
        payload = business_as_dict(record, url=channel_url)
        payload["owner_email"] = email
        payload["owner_secret"] = secret
        return payload

    @app.get("/api/operator/businesses")
    def operator_businesses(request: Request) -> dict[str, object]:
        """Operator console: provisioned businesses (Factory phase 4)."""
        require_human(request)
        from factory_os.domain.flow_canvas import list_rules
        from factory_os.domain.operator_registry import (
            business_as_dict,
            describe_business,
            list_businesses,
            load_business_channels,
        )

        published = {
            rule.tenant_id
            for rule in list_rules(url=(cfg.database_runtime_url or "").strip() or None)
            if rule.status == "published" and rule.tenant_id is not None
        }
        channel_configured = bool(
            cfg.meta_whatsapp_access_token.strip() and cfg.meta_whatsapp_phone_number_id.strip()
        )
        load_business_channels((cfg.database_runtime_url or "").strip() or None)
        channel_url = (cfg.database_runtime_url or "").strip() or None
        described = [
            describe_business(
                item,
                live_tenant_id=runtime().store.tenant_id,
                channel_configured=channel_configured,
                published_tenant_ids=published,
                url=channel_url,
            )
            for item in list_businesses(url=channel_url)
        ]
        return {"businesses": [business_as_dict(item, url=channel_url) for item in described]}

    @app.post("/api/operator/businesses")
    def operator_provision_business(request: Request, body: OperatorProvisionIn) -> dict[str, object]:
        """Create a business from a template without public signup (ADR-019)."""
        require_human(request)
        from factory_os.domain.operator_registry import business_as_dict, list_businesses
        from factory_os.domain.provision import TEMPLATE_MODULES, provision_business

        channel_url = (cfg.database_runtime_url or "").strip() or None
        industry = (body.industry or "").strip().lower()
        if industry not in TEMPLATE_MODULES:
            raise HTTPException(status_code=400, detail=f"unknown_industry:{body.industry}")
        try:
            tid = provision_business(
                name=body.name,
                industry=industry,
                url=channel_url,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        record = next(
            item for item in list_businesses(url=channel_url) if item.tenant_id == tid
        )
        return business_as_dict(record, url=channel_url)

    @app.post("/api/operator/autonomy")
    def operator_set_autonomy(request: Request, body: OperatorAutonomyIn) -> dict[str, object]:
        """Tighten one autonomy grant for a business. Cannot loosen the floor."""
        require_human(request)
        from factory_os.domain.autonomy import set_tenant_autonomy
        from factory_os.domain.operator_registry import list_businesses

        channel_url = (cfg.database_runtime_url or "").strip() or None
        try:
            tid = UUID(body.tenant_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="unknown_business") from exc
        record = next(
            (item for item in list_businesses(url=channel_url) if item.tenant_id == tid),
            None,
        )
        if record is None:
            raise HTTPException(status_code=404, detail="business_not_found")
        try:
            grants = set_tenant_autonomy(
                tid,
                industry=record.industry,
                action=body.action,
                level=body.level,
                url=channel_url,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "tenant_id": str(tid),
            "autonomy": [{"action": item.action, "level": item.level} for item in grants],
        }

    def _operator_tenant(tenant_id: str):
        from factory_os.domain.operator_registry import list_businesses

        channel_url = (cfg.database_runtime_url or "").strip() or None
        try:
            tid = UUID(tenant_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="unknown_business") from exc
        record = next(
            (item for item in list_businesses(url=channel_url) if item.tenant_id == tid),
            None,
        )
        if record is None:
            raise HTTPException(status_code=404, detail="business_not_found")
        return tid, channel_url

    def _employee_http_error(exc: Exception) -> HTTPException:
        if isinstance(exc, KeyError):
            return HTTPException(status_code=404, detail=str(exc))
        return HTTPException(status_code=400, detail=str(exc))

    @app.get("/api/operator/employees")
    def operator_list_employees(request: Request, tenant_id: str) -> dict[str, object]:
        """Per-business digital employee roster (ADR-026)."""
        require_human(request)
        from factory_os.domain.tenant_employees import employee_as_dict, list_employees

        tid, channel_url = _operator_tenant(tenant_id)
        rows = list_employees(tid, url=channel_url)
        return {
            "tenant_id": str(tid),
            "employees": [employee_as_dict(row) for row in rows],
        }

    @app.patch("/api/operator/employees")
    def operator_patch_employee(request: Request, body: OperatorEmployeePatchIn) -> dict[str, object]:
        """Enable/disable or rename a roster row. Locked catalog roles stay on."""
        require_human(request)
        from factory_os.domain.tenant_employees import (
            employee_as_dict,
            set_employee_enabled,
            set_employee_profile,
        )

        tid, channel_url = _operator_tenant(body.tenant_id)
        try:
            row = None
            if body.enabled is not None:
                row = set_employee_enabled(
                    tid, body.employee_key, body.enabled, url=channel_url
                )
            if body.display_name is not None or body.style is not None:
                row = set_employee_profile(
                    tid,
                    body.employee_key,
                    display_name=body.display_name,
                    style=body.style,
                    url=channel_url,
                )
            if row is None:
                raise HTTPException(status_code=400, detail="no_employee_changes")
        except (ValueError, KeyError) as exc:
            raise _employee_http_error(exc) from exc
        return {"tenant_id": str(tid), "employee": employee_as_dict(row)}

    @app.post("/api/operator/employees")
    def operator_clone_employee(request: Request, body: OperatorEmployeeCloneIn) -> dict[str, object]:
        """Clone a catalog base_role. No custom tools (ADR-026)."""
        require_human(request)
        from factory_os.domain.models import EmployeeRole
        from factory_os.domain.tenant_employees import clone_employee, employee_as_dict

        tid, channel_url = _operator_tenant(body.tenant_id)
        try:
            role = EmployeeRole(body.base_role.strip().lower())
            row = clone_employee(
                tid,
                base_role=role,
                display_name=body.display_name,
                style=body.style,
                url=channel_url,
            )
        except (ValueError, KeyError) as exc:
            raise _employee_http_error(exc) from exc
        return {"tenant_id": str(tid), "employee": employee_as_dict(row)}

    @app.delete("/api/operator/employees")
    def operator_archive_employee(
        request: Request, body: OperatorEmployeeArchiveIn
    ) -> dict[str, object]:
        """Soft-archive a clone. Catalog rows are not deleted."""
        require_human(request)
        from factory_os.domain.tenant_employees import archive_employee, employee_as_dict

        tid, channel_url = _operator_tenant(body.tenant_id)
        try:
            row = archive_employee(tid, body.employee_key, url=channel_url)
        except (ValueError, KeyError) as exc:
            raise _employee_http_error(exc) from exc
        return {"tenant_id": str(tid), "employee": employee_as_dict(row)}

    @app.get("/api/owner/employees")
    def owner_list_employees(request: Request) -> dict[str, object]:
        """Owner roster for the signed-in business."""
        from factory_os.domain.tenant_employees import employee_as_dict, list_employees

        owner = _owner_session(request)
        channel_url = (cfg.database_runtime_url or "").strip() or None
        rows = list_employees(owner.tenant_id, url=channel_url)
        return {
            "tenant_id": str(owner.tenant_id),
            "employees": [employee_as_dict(row) for row in rows],
        }

    @app.patch("/api/owner/employees")
    def owner_patch_employee(request: Request, body: OwnerEmployeePatchIn) -> dict[str, object]:
        from factory_os.domain.tenant_employees import (
            employee_as_dict,
            set_employee_enabled,
            set_employee_profile,
        )

        owner = _owner_session(request)
        channel_url = (cfg.database_runtime_url or "").strip() or None
        try:
            row = None
            if body.enabled is not None:
                row = set_employee_enabled(
                    owner.tenant_id, body.employee_key, body.enabled, url=channel_url
                )
            if body.display_name is not None or body.style is not None:
                row = set_employee_profile(
                    owner.tenant_id,
                    body.employee_key,
                    display_name=body.display_name,
                    style=body.style,
                    url=channel_url,
                )
            if row is None:
                raise HTTPException(status_code=400, detail="no_employee_changes")
        except (ValueError, KeyError) as exc:
            raise _employee_http_error(exc) from exc
        return {"tenant_id": str(owner.tenant_id), "employee": employee_as_dict(row)}

    @app.post("/api/owner/employees")
    def owner_clone_employee(request: Request, body: OwnerEmployeeCloneIn) -> dict[str, object]:
        from factory_os.domain.models import EmployeeRole
        from factory_os.domain.tenant_employees import clone_employee, employee_as_dict

        owner = _owner_session(request)
        channel_url = (cfg.database_runtime_url or "").strip() or None
        try:
            role = EmployeeRole(body.base_role.strip().lower())
            row = clone_employee(
                owner.tenant_id,
                base_role=role,
                display_name=body.display_name,
                style=body.style,
                url=channel_url,
            )
        except (ValueError, KeyError) as exc:
            raise _employee_http_error(exc) from exc
        return {"tenant_id": str(owner.tenant_id), "employee": employee_as_dict(row)}

    @app.delete("/api/owner/employees")
    def owner_archive_employee(
        request: Request, body: OwnerEmployeeArchiveIn
    ) -> dict[str, object]:
        from factory_os.domain.tenant_employees import archive_employee, employee_as_dict

        owner = _owner_session(request)
        channel_url = (cfg.database_runtime_url or "").strip() or None
        try:
            row = archive_employee(owner.tenant_id, body.employee_key, url=channel_url)
        except (ValueError, KeyError) as exc:
            raise _employee_http_error(exc) from exc
        return {"tenant_id": str(owner.tenant_id), "employee": employee_as_dict(row)}

    @app.get("/api/operator/diagnosis")
    def operator_diagnosis(request: Request, industry: str, modules: str = "") -> dict[str, object]:
        """Guided process diagnosis for an industry and enabled modules (phase 5)."""
        require_human(request)
        from factory_os.domain.process_catalog import diagnose_processes, diagnosis_as_dict

        enabled = [part.strip() for part in modules.split(",") if part.strip()]
        try:
            rows = diagnose_processes(industry, enabled)
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "industry": industry,
            "modules": enabled,
            "processes": [diagnosis_as_dict(row) for row in rows],
        }

    @app.get("/api/operator/flow-map")
    def operator_flow_map(
        request: Request,
        modules: str = "",
        tenant_id_param: str | None = Query(None, alias="tenant_id"),
    ) -> dict[str, object]:
        """Read-only flow map from enabled modules (phase 6) + employee palette (ADR-027)."""
        require_human(request)
        from factory_os.contracts.employees import CANVAS_MODULES_BY_ROLE
        from factory_os.domain.flow_canvas import (
            attach_team_to_flow,
            build_flow_map,
            flow_map_as_dict,
            get_published_flow_kinds,
            get_published_team,
        )
        from factory_os.domain.operator_registry import get_business
        from factory_os.domain.tenant_config import get_tenant_config
        from factory_os.domain.tenant_employees import employee_as_dict, list_employees

        enabled: list[str]
        published_kinds: tuple[str, ...] | None = None
        published_team = ()
        employee_palette: list[dict[str, object]] = []
        if tenant_id_param:
            try:
                target = UUID(tenant_id_param)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="bad_tenant_id") from exc
            record = get_business(target, url=_database_url())
            if record is None:
                raise HTTPException(status_code=404, detail="tenant_not_found")
            config = get_tenant_config(target, url=_database_url())
            enabled = list(config.modules or record.modules)
            published_kinds = get_published_flow_kinds(target, url=_database_url())
            published_team = get_published_team(target, url=_database_url())
            for row in list_employees(target, include_archived=False, url=_database_url()):
                if not row.enabled:
                    continue
                payload = employee_as_dict(row)
                payload["modules"] = sorted(
                    CANVAS_MODULES_BY_ROLE.get(row.base_role, frozenset())
                )
                employee_palette.append(payload)
        else:
            enabled = [part.strip() for part in modules.split(",") if part.strip()]
        flow = build_flow_map(enabled)
        if published_team:
            flow = attach_team_to_flow(flow, published_team, roster=employee_palette)
        payload = flow_map_as_dict(
            flow,
            published_kinds=published_kinds,
            employee_palette=employee_palette,
            published_team=published_team,
        )
        payload["employee_targets"] = {
            role.value: sorted(modules)
            for role, modules in CANVAS_MODULES_BY_ROLE.items()
        }
        return payload

    @app.post("/api/operator/flow-map/try")
    def operator_try_flow_map(
        request: Request,
        body: OperatorFlowMapPublishIn,
    ) -> dict[str, object]:
        """Validate canvas kinds without publishing (Try before publish)."""
        require_human(request)
        from factory_os.domain.flow_canvas import try_flow_map

        try:
            kinds = try_flow_map(body.kinds)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "kinds": list(kinds), "published": False}

    @app.post("/api/operator/flow-map/propose")
    def operator_propose_flow_map(
        request: Request,
        body: OperatorFlowMapPublishIn,
    ) -> dict[str, object]:
        """Suggest canvas kinds. Never publishes on its own."""
        require_human(request)
        from factory_os.domain.flow_canvas import palette_modules, propose_flow_kinds

        proposed = propose_flow_kinds(body.kinds, palette=palette_modules())
        return {
            "proposal": list(proposed),
            "published": False,
            "message": "Review the proposal on the canvas. Publish only when you confirm.",
        }

    @app.post("/api/operator/flow-map/publish")
    def operator_publish_flow_map(
        request: Request,
        body: OperatorFlowMapPublishIn,
        tenant_id_param: str | None = Query(None, alias="tenant_id"),
    ) -> dict[str, object]:
        """Freeze canvas kinds that drive the WhatsApp turn graph for a business."""
        require_human(request)
        from factory_os.domain.flow_canvas import publish_flow_map
        from factory_os.domain.operator_registry import get_business

        if not tenant_id_param:
            raise HTTPException(status_code=400, detail="tenant_id_required")
        try:
            target = UUID(tenant_id_param)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="bad_tenant_id") from exc
        record = get_business(target, url=_database_url())
        if record is None:
            raise HTTPException(status_code=404, detail="tenant_not_found")
        try:
            kinds = publish_flow_map(
                target,
                body.kinds,
                team=[item.model_dump() for item in body.team],
                url=_database_url(),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        from factory_os.domain.flow_canvas import get_published_team

        team = get_published_team(target, url=_database_url())
        return {
            "published": True,
            "kinds": list(kinds),
            "team": [{"employee_key": row.employee_key, "module": row.module} for row in team],
            "tenant_id": str(target),
        }

    @app.get("/api/shop/modules")
    def shop_modules(request: Request) -> dict[str, object]:
        """Active modules for the signed-in shop. null = unrestricted (legacy pilot)."""
        require_human(request)
        from factory_os.domain.modules import enabled_modules, nav_hrefs_for_modules

        active = enabled_modules(tenant_id(), url=_database_url())
        nav = nav_hrefs_for_modules(active)
        return {
            "modules": list(active) if active is not None else None,
            "nav_hrefs": sorted(nav) if nav is not None else None,
        }

    @app.get("/api/operator/rules")
    def operator_list_rules(request: Request) -> dict[str, object]:
        """Catalog rules the guarded canvas can show."""
        require_human(request)
        from factory_os.domain.flow_canvas import list_rules, rule_as_dict

        return {
            "rules": [
                rule_as_dict(rule)
                for rule in list_rules(url=(cfg.database_runtime_url or "").strip() or None)
            ]
        }

    @app.post("/api/operator/rules")
    def operator_create_rule(request: Request, body: OperatorRuleIn) -> dict[str, object]:
        require_human(request)
        from factory_os.domain.flow_canvas import create_rule, rule_as_dict

        try:
            rule = create_rule(
                when_event=body.when_event,
                if_threshold=body.if_threshold,
                then_action=body.then_action,
                tenant_id=tenant_id(),
                url=(cfg.database_runtime_url or "").strip() or None,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return rule_as_dict(rule)

    @app.post("/api/operator/rules/{rule_id}/publish")
    def operator_publish_rule(request: Request, rule_id: UUID) -> dict[str, object]:
        require_human(request)
        from factory_os.domain.flow_canvas import publish_rule, rule_as_dict

        try:
            rule = publish_rule(rule_id, url=(cfg.database_runtime_url or "").strip() or None)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="rule_not_found") from exc
        return rule_as_dict(rule)

    @app.post("/api/operator/rules/{rule_id}/revise")
    def operator_revise_rule(request: Request, rule_id: UUID, body: OperatorReviseIn) -> dict[str, object]:
        require_human(request)
        from factory_os.domain.flow_canvas import rule_as_dict, update_rule

        try:
            rule = update_rule(
                rule_id,
                then_action=body.then_action,
                url=(cfg.database_runtime_url or "").strip() or None,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="rule_not_found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return rule_as_dict(rule)

    @app.post("/api/operator/rules/{rule_id}/revert")
    def operator_revert_rule(request: Request, rule_id: UUID, body: OperatorRevertIn) -> dict[str, object]:
        require_human(request)
        from factory_os.domain.flow_canvas import revert_rule, rule_as_dict

        try:
            rule = revert_rule(
                rule_id,
                version=body.version,
                url=(cfg.database_runtime_url or "").strip() or None,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="rule_not_found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return rule_as_dict(rule)

    @app.post("/api/operator/connections")
    def operator_connect(request: Request, body: OperatorConnectIn) -> dict[str, object]:
        require_human(request)
        from factory_os.domain.flow_canvas import connect_modules

        try:
            edge = connect_modules(body.source, body.target, body.port)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "source": edge.source,
            "target": edge.target,
            "port": edge.port,
            "locked": edge.locked,
        }

    @app.post("/api/panel/users")
    def post_panel_user(body: PanelUserIn, request: Request) -> dict[str, str]:
        from factory_os.domain.panel_access import (
            clean_job_title,
            hash_panel_secret,
            new_secret_salt,
            roles_assignable_by,
        )

        actor = require_owner(request)
        secret = body.secret.strip()
        if len(secret) < 8:
            raise HTTPException(status_code=400, detail="short_secret")
        if body.role not in roles_assignable_by(actor.role):
            if body.role in {"owner", "supervisor", "staff"}:
                raise HTTPException(status_code=403, detail="panel_forbidden")
            raise HTTPException(status_code=400, detail="bad_role")
        try:
            job_title = clean_job_title(body.role, body.job_title)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="bad_job") from exc
        salt = new_secret_salt()
        pin_raw = (body.pin or "").strip()
        pin_salt: str | None = None
        pin_hash: str | None = None
        if pin_raw:
            pin_salt = new_secret_salt()
            pin_hash = hash_panel_secret(pin_raw, pin_salt)
        try:
            user = runtime().store.add_panel_user(
                tenant_id(),
                body.name,
                body.email,
                body.role,
                salt,
                hash_panel_secret(secret, salt),
                pin_salt=pin_salt,
                pin_hash=pin_hash,
                job_title=job_title,
            )
        except ValueError as exc:
            code = str(exc)
            status = 409 if code == "duplicate_email" else 400
            raise HTTPException(status_code=status, detail=code) from exc
        return _public_panel_user(user)

    @app.post("/api/panel/users/{user_id}/secret")
    def post_panel_user_secret(
        user_id: UUID, body: PanelSecretResetIn, request: Request
    ) -> dict[str, str]:
        from factory_os.domain.panel_access import hash_panel_secret, new_secret_salt

        actor = require_human(request)
        if actor.role != "admin":
            raise HTTPException(status_code=403, detail="panel_forbidden")
        secret = body.secret.strip()
        if len(secret) < 8:
            raise HTTPException(status_code=400, detail="short_secret")
        salt = new_secret_salt()
        try:
            user = runtime().store.set_panel_user_secret(
                tenant_id(),
                user_id,
                salt,
                hash_panel_secret(secret, salt),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="user_not_found") from exc
        return _public_panel_user(user)

    @app.get("/api/panel/audit")
    def get_panel_audit(request: Request) -> dict[str, object]:
        require_owner(request)
        events = runtime().store.list_human_audit(tenant_id())[-100:]
        return {
            "events": [
                {
                    "id": str(event.id),
                    "actor_id": str(event.actor_id) if event.actor_id else None,
                    "actor_name": event.actor_name,
                    "actor_role": event.actor_role,
                    "method": event.method,
                    "path": event.path,
                    "created_at": event.created_at.isoformat() if event.created_at else None,
                }
                for event in events
            ]
        }

    @app.get("/health")
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "service": "factory-os-api",
            "shop": "postgres" if cfg.database_url else "memory",
        }

    @app.post("/turns")
    def turns(body: TurnIn) -> dict[str, str | bool]:
        result = runtime().handle_turn(tenant_id(), body.wa_number, body.text)
        return {
            "employee": result.employee,
            "role": result.role,
            "reply": result.reply,
            "conversation_id": result.conversation_id,
            "needs_human": result.needs_human,
            "human_takeover": result.human_takeover,
        }

    @app.post("/payments/fake-confirm")
    def fake_confirm(provider_ref: str, request: Request) -> dict[str, str]:
        if cfg.app_env.strip().lower() != "test":
            raise HTTPException(status_code=404, detail="not_found")
        require_human(request)
        shop_rt = runtime()
        if getattr(shop_rt.payments, "name", "") != "fake":
            raise HTTPException(status_code=400, detail="fake_confirm_only_for_fake_provider")
        shop_rt.confirm_payment_from_adapter(provider_ref)
        return {"status": "confirmed", "provider_ref": provider_ref}

    @app.post("/webhooks/payments/fake")
    async def inbound_payment_fake(request: Request) -> dict[str, str]:
        if cfg.app_env.strip().lower() != "test":
            raise HTTPException(status_code=404, detail="not_found")
        require_human(request)
        raw = await request.body()
        shop_rt = runtime()
        if getattr(shop_rt.payments, "name", "") != "fake":
            raise HTTPException(status_code=400, detail="wrong_provider")
        try:
            return shop_rt.apply_payment_webhook(raw, dict(request.headers))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/webhooks/payments/baneco")
    async def inbound_payment_baneco(request: Request) -> dict[str, str]:
        raw = await request.body()
        shop_rt = runtime()
        if getattr(shop_rt.payments, "name", "") != "baneco":
            raise HTTPException(status_code=400, detail="baneco_provider_not_active")
        try:
            return shop_rt.apply_payment_webhook(raw, dict(request.headers))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/webhooks/whatsapp")
    def verify_whatsapp(
        hub_mode: str | None = Query(default=None, alias="hub.mode"),
        hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
        hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
    ) -> PlainTextResponse:
        if (
            hub_mode == "subscribe"
            and cfg.meta_whatsapp_verify_token
            and hub_verify_token == cfg.meta_whatsapp_verify_token
            and hub_challenge
        ):
            return PlainTextResponse(hub_challenge)
        raise HTTPException(status_code=403, detail="verify failed")

    @app.post("/webhooks/whatsapp")
    async def inbound_whatsapp(request: Request, background: BackgroundTasks) -> dict[str, str]:
        raw = await request.body()
        header = request.headers.get("x-hub-signature-256", "")
        if not cfg.meta_whatsapp_app_secret.strip():
            raise HTTPException(status_code=503, detail="meta_signature_not_configured")
        if not _valid_meta_signature(cfg.meta_whatsapp_app_secret, raw, header):
            raise HTTPException(status_code=403, detail="bad signature")
        try:
            payload = json.loads(raw.decode() or "{}")
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="invalid json") from exc
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="invalid json")
        from factory_os.domain.operator_registry import (
            list_businesses,
            load_business_channels,
            reserved_tenant_for_payload,
        )

        load_business_channels((cfg.database_runtime_url or "").strip() or None)
        reserved_id = reserved_tenant_for_payload(payload, live_tenant_id=runtime().store.tenant_id)
        if reserved_id is not None:
            industry = "cafe"
            for item in list_businesses(url=(cfg.database_runtime_url or "").strip() or None):
                if item.tenant_id == reserved_id:
                    industry = item.industry
                    break
            from factory_os.agents.reserved_shop import (
                answer_reserved,
                deliver_reserved,
                mark_reserved_delivered,
            )
            from factory_os.domain.operator_registry import phone_for_tenant, token_for_tenant

            channel_url = (cfg.database_runtime_url or "").strip() or None
            for msg in parse_inbound(payload):
                if msg.message_id and not claimer.claim(
                    msg.message_id, wa_number=msg.wa_number, tenant_id=str(reserved_id)
                ):
                    continue
                reply = answer_reserved(
                    reserved_id,
                    industry=industry,
                    wa_number=msg.wa_number,
                    text=msg.text,
                    url=channel_url,
                )
                token = token_for_tenant(reserved_id)
                phone = phone_for_tenant(reserved_id)
                if token and phone and reply:
                    try:
                        deliver_reserved(token, phone, msg.wa_number, reply)
                    except Exception:
                        import logging

                        logging.getLogger(__name__).exception("reserved whatsapp send failed")
                    else:
                        mark_reserved_delivered(reserved_id, url=channel_url)
            return {"status": "ok"}
        tid = str(tenant_id())
        for msg in parse_inbound(payload):
            if msg.message_id and not claimer.claim(
                msg.message_id, wa_number=msg.wa_number, tenant_id=tid
            ):
                continue
            background.add_task(
                _process_whatsapp_inbound,
                msg.wa_number,
                msg.text,
                msg.message_id,
                media_id=msg.media_id,
                media_kind=msg.media_kind,
                mime=msg.mime,
                filename=msg.filename,
                caption=msg.caption,
            )
        return {"status": "ok"}

    @app.get("/inbox")
    def inbox() -> FileResponse:
        if not INBOX_PATH.is_file():
            raise HTTPException(status_code=500, detail="inbox missing")
        return FileResponse(
            INBOX_PATH,
            media_type="text/html",
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/api/conversations")
    def list_conversations(request: Request) -> dict[str, object]:
        require_human(request)
        shop_rt = runtime()
        items = shop_rt.store.list_conversations(tenant_id())
        return {"conversations": [_summary(shop_rt, item) for item in items]}

    @app.get("/api/conversations/{conversation_id}")
    def get_conversation(conversation_id: str, request: Request) -> dict[str, object]:
        require_human(request)
        shop_rt = runtime()
        try:
            conv = shop_rt.store.get_conversation(tenant_id(), UUID(conversation_id))
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="conversation") from exc
        if conv is None:
            raise HTTPException(status_code=404, detail="conversation")
        return _detail(shop_rt, conv)

    @app.post("/api/conversations/{conversation_id}/takeover")
    def takeover(conversation_id: str, request: Request) -> dict[str, object]:
        require_human(request)
        shop_rt = runtime()
        try:
            conv = shop_rt.set_takeover(tenant_id(), UUID(conversation_id), True)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=404, detail="conversation") from exc
        return _detail(shop_rt, conv)

    @app.post("/api/conversations/{conversation_id}/release")
    def release(conversation_id: str, request: Request) -> dict[str, object]:
        require_human(request)
        shop_rt = runtime()
        try:
            conv = shop_rt.set_takeover(tenant_id(), UUID(conversation_id), False)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=404, detail="conversation") from exc
        return _detail(shop_rt, conv)

    @app.post("/api/conversations/{conversation_id}/reply")
    def reply(conversation_id: str, body: ReplyIn, request: Request) -> dict[str, object]:
        require_human(request)
        shop_rt = runtime()
        text = body.text.strip()
        if not text:
            raise HTTPException(status_code=400, detail="empty")
        try:
            conv = shop_rt.human_reply(tenant_id(), UUID(conversation_id), text)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="conversation") from exc
        return _detail(shop_rt, conv)

    @app.post("/api/conversations/{conversation_id}/media/{media_id}/enrich")
    def enrich_conversation_media_endpoint(
        conversation_id: str, media_id: str, request: Request
    ) -> dict[str, object]:
        """Staff-facing transcript/summary; never confirms payment (ADR-015 Fase E)."""
        from factory_os.domain.media_enrichment import enrich_conversation_media

        require_human(request)
        shop_rt = runtime()
        tenant = tenant_id()
        try:
            cid = UUID(conversation_id)
            mid = UUID(media_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="media") from exc
        conv = shop_rt.store.get_conversation(tenant, cid)
        if conv is None:
            raise HTTPException(status_code=404, detail="conversation")
        link = shop_rt.store.get_conversation_media(tenant, mid)
        if link is None or link.conversation_id != cid:
            raise HTTPException(status_code=404, detail="media")
        enrich_conversation_media(
            shop_rt.store,
            tenant,
            mid,
            enricher=media_enricher,
        )
        refreshed = shop_rt.store.get_conversation(tenant, cid) or conv
        return _detail(shop_rt, refreshed)

    @app.post("/api/conversations/{conversation_id}/media")
    async def send_conversation_media(conversation_id: str, request: Request) -> dict[str, object]:
        """Staff outbound image/document while human_takeover (ADR-015 Fase C)."""
        from factory_os.domain.chat_media import ChatMediaError, store_outbound_chat_media
        from factory_os.domain.media import read_media_bytes

        actor = require_human(request)
        shop_rt = runtime()
        tenant = tenant_id()
        try:
            cid = UUID(conversation_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="conversation") from exc
        conv = shop_rt.store.get_conversation(tenant, cid)
        if conv is None:
            raise HTTPException(status_code=404, detail="conversation")
        if not conv.state.human_takeover:
            raise HTTPException(status_code=409, detail="takeover_required")
        customer = shop_rt.store.get_customer(tenant, conv.customer_id)
        if customer is None:
            raise HTTPException(status_code=404, detail="conversation")

        content_type_header = request.headers.get("content-type", "")
        if not content_type_header.split(";", 1)[0].strip().lower().startswith("multipart/"):
            raise HTTPException(status_code=400, detail="empty_file")
        try:
            fields = _multipart_fields(await request.body(), content_type_header)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="empty_file") from exc
        upload: tuple[str | None, str, bytes] | None = None
        caption = ""
        for name, upload_name, part_type, data in fields:
            if name == "file" and upload is None:
                upload = (upload_name, part_type, data)
            elif name == "caption" and data:
                caption = data.decode("utf-8", errors="replace").strip()
        if upload is None or not upload[2]:
            raise HTTPException(status_code=400, detail="empty_file")
        upload_name, part_type, data = upload
        part_mime = (part_type or "").split(";", 1)[0].strip().lower()
        kind = "image" if part_mime.startswith("image/") else "document"
        note = caption or (upload_name or "archivo")
        shop_rt.store.append_message(conv, "Humano", note)
        msg_index = max(0, len(conv.messages) - 1)
        try:
            link, asset = store_outbound_chat_media(
                shop_rt.store,
                tenant,
                conversation_id=conv.id,
                kind=kind,
                data=data,
                mime=part_mime or None,
                filename=upload_name,
                message_index=msg_index,
                uploaded_by=actor.name,
            )
        except ChatMediaError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        payload = read_media_bytes(asset.storage_key)
        channel = shop_rt.channel
        if kind == "image":
            channel.send_image(
                customer.wa_number,
                content=payload,
                mime=asset.mime,
                filename=link.filename or "image.png",
                caption=caption,
            )
        else:
            send_doc = getattr(channel, "send_document", None)
            if callable(send_doc):
                send_doc(
                    customer.wa_number,
                    content=payload,
                    mime=asset.mime,
                    filename=link.filename or "file.pdf",
                    caption=caption,
                )
            else:
                channel.send_text(customer.wa_number, note)
        shop_rt.store.save_conversation_state(conv)
        refreshed = shop_rt.store.get_conversation(tenant, conv.id) or conv
        return _detail(shop_rt, refreshed)

    @app.post("/api/conversations/{conversation_id}/close")
    def close_chat(conversation_id: str, body: ChatCloseIn, request: Request) -> dict[str, object]:
        require_human(request)
        from factory_os.domain.chat_close import ChatCloseError, apply_chat_close

        shop_rt = runtime()
        try:
            conv = shop_rt.store.get_conversation(tenant_id(), UUID(conversation_id))
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="conversation") from exc
        if conv is None:
            raise HTTPException(status_code=404, detail="conversation")
        try:
            action = apply_chat_close(shop_rt.store, conv, body.action.strip())
        except ChatCloseError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.code) from exc
        except ValueError as exc:
            code = str(exc)
            if code in {"out_of_stock", "unknown_variant"}:
                raise HTTPException(status_code=409, detail=code) from exc
            raise
        shop_rt.store.save_conversation_state(conv)
        payload = _detail(shop_rt, conv)
        payload["action"] = action
        payload["payment_id"] = str(conv.state.payment_id) if conv.state.payment_id else ""
        return payload

    @app.get("/api/orders")
    def list_orders(request: Request, q: str = "") -> dict[str, object]:
        require_human(request)
        shop_rt = runtime()
        from factory_os.domain.order_hold import release_expired_unpaid_orders

        release_expired_unpaid_orders(shop_rt.store, tenant_id())
        needle = q.strip().lower()
        orders = []
        for order in shop_rt.store.list_orders(tenant_id()):
            if getattr(order, "origin", "agent") == "counter":
                continue
            row = _order_row(shop_rt.store, tenant_id(), order)
            if needle and not any(
                needle in field
                for field in (
                    str(row["customer_name"] or "").lower(),
                    str(row["wa_number"] or "").lower(),
                    str(row["public_number"] or "").lower(),
                    str(row["id"]).lower(),
                )
            ):
                continue
            orders.append(row)
        return {"orders": orders}

    @app.post("/api/orders")
    def create_manual_order(body: ManualOrderIn, request: Request) -> dict[str, object]:
        """Owner records a sale already paid in cash. Does not confirm Baneco."""
        require_human(request)
        from factory_os.domain.owner_orders import OwnerOrderError, create_manual_cash_order

        shop_rt = runtime()
        try:
            result = create_manual_cash_order(
                shop_rt.store,
                tenant_id(),
                wa_number=body.wa_number,
                name=body.name,
                address=body.address,
                lines=_manual_lines(body.items),
                recipient_name=body.recipient_name,
                delivery_address=body.delivery_address,
            )
        except OwnerOrderError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.code) from exc
        return _order_row(shop_rt.store, tenant_id(), result.order)

    @app.patch("/api/orders/{order_id}")
    def patch_order(order_id: str, body: OrderPatchIn, request: Request) -> dict[str, object]:
        require_human(request)
        from factory_os.domain.owner_orders import OwnerOrderError, update_manual_order

        try:
            oid = UUID(order_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="invalid_order_id") from exc
        shop_rt = runtime()
        try:
            result = update_manual_order(
                shop_rt.store,
                tenant_id(),
                oid,
                name=body.name,
                address=body.address,
                lines=None if body.items is None else _manual_lines(body.items),
                recipient_name=body.recipient_name,
                delivery_address=body.delivery_address,
                mark_cash_paid=body.mark_cash_paid,
            )
        except OwnerOrderError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.code) from exc
        return _order_row(shop_rt.store, tenant_id(), result.order)

    def _entity_attachments_payload(
        store, tenant: UUID, entity_type: str, entity_id: UUID
    ) -> dict[str, object]:
        from factory_os.domain.entity_media import entity_media_view

        rows = store.list_entity_media(tenant, entity_type, entity_id)
        out: list[dict[str, object]] = []
        for link in rows:
            asset = store.get_media_asset(tenant, link.asset_id)
            out.append(entity_media_view(link, asset))
        return {"attachments": out}

    async def _read_attachment_upload(
        request: Request,
    ) -> tuple[str | None, str, bytes, str | None]:
        content_type_header = request.headers.get("content-type", "")
        if not content_type_header.split(";", 1)[0].strip().lower().startswith("multipart/"):
            raise HTTPException(status_code=400, detail="empty_file")
        try:
            fields = _multipart_fields(await request.body(), content_type_header)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="empty_file") from exc
        upload: tuple[str | None, str, bytes] | None = None
        note: str | None = None
        for name, upload_name, part_type, data in fields:
            if name == "file" and upload is None:
                upload = (upload_name, part_type, data)
            elif name == "note" and data:
                note = data.decode("utf-8", errors="replace").strip() or None
        if upload is None or not upload[2]:
            raise HTTPException(status_code=400, detail="empty_file")
        upload_name, part_type, data = upload
        return upload_name, part_type, data, note

    @app.get("/api/orders/{order_id}/attachments")
    def list_order_attachments(order_id: str, request: Request) -> dict[str, object]:
        require_human(request)
        try:
            oid = UUID(order_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="order_not_found") from exc
        shop_rt = runtime()
        tenant = tenant_id()
        if shop_rt.store.get_order(tenant, oid) is None:
            raise HTTPException(status_code=404, detail="order_not_found")
        return _entity_attachments_payload(shop_rt.store, tenant, "order", oid)

    @app.post("/api/orders/{order_id}/attachments")
    async def post_order_attachment(order_id: str, request: Request) -> dict[str, object]:
        """Attach image/pdf to a customer order. Does not confirm payment or change status."""
        from factory_os.domain.entity_media import EntityMediaError, store_entity_attachment

        actor = require_human(request)
        try:
            oid = UUID(order_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="order_not_found") from exc
        shop_rt = runtime()
        tenant = tenant_id()
        if shop_rt.store.get_order(tenant, oid) is None:
            raise HTTPException(status_code=404, detail="order_not_found")
        upload_name, part_type, data, note = await _read_attachment_upload(request)
        part_mime = (part_type or "").split(";", 1)[0].strip().lower() or None
        try:
            store_entity_attachment(
                shop_rt.store,
                tenant,
                entity_type="order",
                entity_id=oid,
                data=data,
                mime=part_mime,
                filename=upload_name,
                uploaded_by=actor.name,
                note=note,
            )
        except EntityMediaError as exc:
            code = str(exc) or "bad_type"
            if code == "unknown_entity":
                raise HTTPException(status_code=404, detail="order_not_found") from exc
            raise HTTPException(status_code=400, detail=code) from exc
        return _entity_attachments_payload(shop_rt.store, tenant, "order", oid)

    @app.post("/api/orders/{order_id}/delivery")
    def register_order_delivery(order_id: str, body: DeliveryIn, request: Request) -> dict[str, object]:
        require_human(request)
        shop_rt = runtime()
        try:
            oid = UUID(order_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="order_not_found") from exc
        order = shop_rt.store.get_order(tenant_id(), oid)
        if order is None:
            raise HTTPException(status_code=404, detail="order_not_found")
        recipient_name = body.recipient_name.strip()
        address = body.address.strip()
        if not recipient_name or not address:
            raise HTTPException(status_code=400, detail="empty")
        if shop_rt.store.delivery_for_order(tenant_id(), oid) is not None:
            raise HTTPException(status_code=409, detail="delivery_exists")
        payment = shop_rt.store.payment_for_order(tenant_id(), oid)
        if payment is None or payment.status is not PaymentStatus.CONFIRMED:
            raise HTTPException(status_code=409, detail="payment_not_confirmed")
        customer = shop_rt.store.get_customer(tenant_id(), order.customer_id)
        if customer is None:
            raise HTTPException(status_code=404, detail="order_not_found")
        delivery = shop_rt.store.create_delivery(tenant_id(), oid, address, recipient_name)
        updated = shop_rt.store.update_customer(
            tenant_id(),
            customer.wa_number,
            None if (customer.name or "").strip() else recipient_name,
            None if (customer.address or "").strip() else address,
        )
        return {
            "order_id": str(order.id),
            "delivery": {"address": delivery.address, "recipient_name": delivery.recipient_name},
            "customer": {
                "name": updated.name,
                "address": updated.address,
                "wa_number": updated.wa_number,
            },
        }

    @app.post("/api/orders/{order_id}/delivered")
    def mark_order_delivered(order_id: str, request: Request) -> dict[str, object]:
        require_human(request)
        shop_rt = runtime()
        try:
            oid = UUID(order_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="invalid_order_id") from exc
        try:
            order = shop_rt.store.mark_order_delivered(
                tenant_id(), oid, delivered_by="owner_dashboard"
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="order_not_found") from exc
        return {
            "id": str(order.id),
            "public_number": order.public_number,
            "status": order.status,
            "delivered_at": order.delivered_at.isoformat() if order.delivered_at else None,
            "delivered_by": order.delivered_by,
        }

    @app.post("/api/orders/{order_id}/status")
    def set_order_status(order_id: str, body: OrderStatusIn, request: Request) -> dict[str, object]:
        require_human(request)
        shop_rt = runtime()
        try:
            oid = UUID(order_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="invalid_order_id") from exc
        try:
            order = shop_rt.store.set_order_status(
                tenant_id(), oid, body.status.strip().lower(), delivered_by="owner_dashboard"
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="order_not_found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="bad_status") from exc
        return {
            "id": str(order.id),
            "public_number": order.public_number,
            "status": order.status,
            "delivered_at": order.delivered_at.isoformat() if order.delivered_at else None,
            "delivered_by": order.delivered_by,
        }

    @app.get("/api/catalog")
    def list_catalog(request: Request, limit: int = 50, q: str = "") -> dict[str, object]:
        require_human(request)
        shop_rt = runtime()
        sold = shop_rt.store.sold_units_by_sku(tenant_id())
        needle = q.strip().casefold()
        cap = max(1, min(limit, 200))
        items: list[dict[str, object]] = []
        for record in shop_rt.store.iter_variants():
            row = _catalog_row(
                record,
                int(sold.get(record.variant_sku, 0)),
                store=shop_rt.store,
                tenant=tenant_id(),
            )
            if needle and not _catalog_matches(row, needle):
                continue
            items.append(row)
            if len(items) >= cap:
                break
        return {"products": items}

    @app.post("/api/catalog")
    def add_catalog_item(body: CatalogIn, request: Request) -> dict[str, object]:
        require_human(request)
        codigo = "".join(body.codigo.lower().split())
        name = body.name.strip()
        if not codigo or not name:
            raise HTTPException(status_code=400, detail="codigo_and_name_required")
        price = _parse_catalog_price(body.price)
        if body.stock < 0:
            raise HTTPException(status_code=400, detail="bad_price")
        shop_rt = runtime()
        talla = body.talla.strip()
        color = body.color.strip()
        variant_sku = (
            make_variant_sku(codigo, talla, color, set()) if talla or color else codigo
        )
        attrs = {
            "codigo": codigo,
            "codigo_referencia": body.codigo_referencia.strip() or codigo,
            "category": (body.category or "general").strip() or "general",
            "subcategory": body.subcategory.strip(),
            "brand": body.brand.strip(),
            "material": body.material.strip(),
            "season": body.season.strip(),
            "style": body.style.strip(),
            "talla": talla,
            "color": color,
            "image_url": body.image_url.strip(),
            "tracks_stock": body.tracks_stock,
        }
        attrs = {
            key: value
            for key, value in attrs.items()
            if value or key == "tracks_stock"
        }
        record = VariantRecord(
            product_sku=codigo,
            variant_sku=variant_sku,
            name=name,
            description=body.description.strip(),
            category=attrs.get("category") or "general",
            attributes=attrs,
            price=price,
            currency=(body.currency or "BOB").strip() or "BOB",
            stock=body.stock,
            tokens=tokenize(
                " ".join(
                    [
                        name,
                        body.description,
                        codigo,
                        body.category,
                        body.subcategory,
                        body.brand,
                        body.material,
                        body.season,
                        body.style,
                        talla,
                        color,
                    ]
                )
            ),
        )
        stored = shop_rt.store.put_variant(tenant_id(), record)
        return {
            "variant_sku": stored.variant_sku,
            "codigo": codigo,
            "name": stored.name,
            "price": str(stored.price),
            "stock": stored.stock,
            "tracks_stock": body.tracks_stock,
            "available": True,
            "sold": False,
        }

    @app.get("/api/catalog/categories")
    def list_catalog_categories(request: Request) -> dict[str, object]:
        require_human(request)
        from factory_os.domain.catalog_categories import list_category_rows

        shop_rt = runtime()
        return {"categories": list_category_rows(shop_rt.store, tenant_id())}

    @app.patch("/api/catalog/categories")
    def sort_catalog_category(body: CategorySortIn, request: Request) -> dict[str, object]:
        require_human(request)
        from factory_os.domain.catalog_categories import list_category_rows, parse_category_sort

        shop_rt = runtime()
        try:
            name, sort_order = parse_category_sort(body.name, body.sort_order)
            shop_rt.store.set_category_sort(tenant_id(), name, sort_order)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"categories": list_category_rows(shop_rt.store, tenant_id())}

    def _combo_http(exc: ValueError) -> HTTPException:
        code = str(exc) or "bad_combo"
        if code == "unknown_variant":
            status = 404
        elif code in {"combo_exists", "combo_price_locked"}:
            status = 409
        else:
            status = 400
        return HTTPException(status_code=status, detail=code)

    @app.get("/api/catalog/modifiers")
    def list_catalog_modifiers(request: Request) -> dict[str, object]:
        require_human(request)
        from factory_os.domain.modifiers import list_modifier_payloads

        return {"modifiers": list_modifier_payloads(runtime().store, tenant_id())}

    @app.post("/api/catalog/modifiers")
    def post_catalog_modifier(body: ModifierIn, request: Request) -> dict[str, str]:
        require_supervisor(request)
        from factory_os.domain.modifiers import create_modifier, modifier_payload

        try:
            row = create_modifier(
                runtime().store,
                tenant_id(),
                name=body.name,
                price_delta=body.price_delta,
                currency=body.currency,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc) or "bad_modifier") from exc
        return modifier_payload(row)

    @app.post("/api/catalog/combos")
    def post_catalog_combo(body: ComboIn, request: Request) -> dict[str, object]:
        actor = require_supervisor(request)
        _require_pin_if_configured(actor, body.pin, tenant=tenant_id())
        from factory_os.domain.combos import combo_payload, create_combo

        try:
            record = create_combo(
                runtime().store,
                tenant_id(),
                codigo=body.codigo,
                name=body.name,
                price=body.price,
                category=body.category,
                currency=body.currency,
                components=[item.model_dump() for item in body.components],
                event_date=body.event_date,
            )
        except ValueError as exc:
            raise _combo_http(exc) from exc
        return combo_payload(record)

    @app.patch("/api/catalog/combos/{variant_sku}")
    def patch_catalog_combo(
        variant_sku: str, body: ComboPatchIn, request: Request
    ) -> dict[str, object]:
        actor = require_supervisor(request)
        _require_pin_if_configured(actor, body.pin, tenant=tenant_id())
        from factory_os.domain.combos import combo_payload, update_combo

        try:
            record = update_combo(
                runtime().store,
                tenant_id(),
                variant_sku,
                name=body.name,
                price=body.price,
                category=body.category,
                components=(
                    None if body.components is None else [item.model_dump() for item in body.components]
                ),
                event_date=body.event_date,
            )
        except ValueError as exc:
            raise _combo_http(exc) from exc
        return combo_payload(record)

    @app.patch("/api/catalog/{variant_sku}")
    def patch_catalog_item(
        variant_sku: str, body: CatalogPatchIn, request: Request
    ) -> dict[str, object]:
        require_human(request)
        shop_rt = runtime()
        tenant = tenant_id()
        existing = shop_rt.store.get_variant(tenant, variant_sku)
        if existing is None:
            raise HTTPException(status_code=404, detail="variant_not_found")
        from factory_os.domain.combos import is_combo

        if is_combo(existing) and (body.price is not None or body.stock is not None):
            raise HTTPException(status_code=409, detail="combo_price_locked")
        if body.stock is not None and body.stock < 0:
            raise HTTPException(status_code=400, detail="bad_stock")
        name = existing.name
        if body.name is not None:
            name = body.name.strip()
            if not name:
                raise HTTPException(status_code=400, detail="bad_name")
        description = existing.description if body.description is None else body.description.strip()
        category = existing.category
        if body.category is not None:
            category = body.category.strip() or "general"
        price = existing.price if body.price is None else _parse_catalog_price(body.price)
        currency = existing.currency
        if body.currency is not None:
            currency = body.currency.strip() or "BOB"
        stock = existing.stock if body.stock is None else body.stock
        attrs = dict(existing.attributes)
        for field in _CATALOG_ATTR_FIELDS:
            value = getattr(body, field)
            if value is None:
                continue
            cleaned = value.strip()
            if cleaned:
                attrs[field] = cleaned
            else:
                attrs.pop(field, None)
        if body.category is not None:
            attrs["category"] = category
        codigo = str(attrs.get("codigo") or existing.product_sku)
        record = VariantRecord(
            product_sku=existing.product_sku,
            variant_sku=existing.variant_sku,
            name=name,
            description=description,
            category=category,
            attributes=attrs,
            price=price,
            currency=currency,
            stock=stock,
            tokens=tokenize(
                " ".join(
                    [
                        name,
                        description,
                        codigo,
                        category,
                        str(attrs.get("subcategory") or ""),
                        str(attrs.get("brand") or ""),
                        str(attrs.get("material") or ""),
                        str(attrs.get("season") or ""),
                        str(attrs.get("style") or ""),
                        str(attrs.get("talla") or ""),
                        str(attrs.get("color") or ""),
                        existing.product_sku,
                        existing.variant_sku,
                    ]
                )
            ),
            supplier_id=existing.supplier_id,
            reorder_threshold=existing.reorder_threshold,
        )
        stored = shop_rt.store.put_variant(tenant, record)
        units = int(shop_rt.store.sold_units_by_sku(tenant).get(stored.variant_sku, 0))
        return _catalog_row(stored, units, store=shop_rt.store, tenant=tenant)

    @app.post("/api/catalog/{variant_sku}/image")
    async def upload_catalog_image(variant_sku: str, request: Request) -> dict[str, object]:
        """Store photo as a media asset; first image is primary (ADR-015)."""
        from datetime import UTC, datetime
        from uuid import uuid4

        from factory_os.domain.media import media_thumb_url, store_catalog_media_image
        from factory_os.domain.models import MediaAsset, ProductMedia

        actor = require_human(request)
        shop_rt = runtime()
        tenant = tenant_id()
        record = shop_rt.store.get_variant(tenant, variant_sku)
        if record is None:
            raise HTTPException(status_code=404, detail="unknown_variant")
        content_type_header = request.headers.get("content-type", "")
        if not content_type_header.split(";", 1)[0].strip().lower().startswith("multipart/"):
            raise HTTPException(status_code=400, detail="empty_file")
        try:
            fields = _multipart_fields(await request.body(), content_type_header)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="empty_file") from exc
        upload: tuple[str | None, str, bytes] | None = None
        for name, _upload_name, _part_type, data in fields:
            if name == "file" and upload is None:
                upload = (_upload_name, _part_type, data)
        if upload is None or not upload[2]:
            raise HTTPException(status_code=400, detail="empty_file")
        try:
            stored = store_catalog_media_image(tenant, record.product_sku, upload[2])
            asset = shop_rt.store.add_media_asset(
                tenant,
                MediaAsset(
                    id=uuid4(),
                    tenant_id=tenant,
                    kind="image",
                    mime=stored.mime,
                    size_bytes=stored.size_bytes,
                    storage_key=stored.storage_key,
                    thumb_key=stored.thumb_key,
                    origin="catalog",
                    uploaded_by=actor.name,
                    created_at=datetime.now(UTC),
                ),
            )
            existing = shop_rt.store.list_product_media(tenant, record.product_sku)
            is_primary = len(existing) == 0
            shop_rt.store.add_product_media(
                tenant,
                ProductMedia(
                    id=uuid4(),
                    tenant_id=tenant,
                    product_sku=record.product_sku,
                    asset_id=asset.id,
                    is_primary=is_primary,
                    sort_order=len(existing),
                    created_at=datetime.now(UTC),
                ),
            )
            if is_primary:
                shop_rt.store.set_product_image_paths(
                    tenant, record.product_sku, stored.storage_key, stored.thumb_key
                )
        except ValueError as exc:
            code = str(exc)
            status = 404 if code in {"unknown_product", "unknown_variant", "unknown_media"} else 400
            raise HTTPException(status_code=status, detail=code) from exc
        return {
            "variant_sku": variant_sku,
            "asset_id": str(asset.id),
            "thumb_url": media_thumb_url(asset.id),
            "image_path": stored.storage_key,
            "thumb_path": stored.thumb_key,
        }

    @app.get("/api/catalog/{variant_sku}/media")
    def list_catalog_media(variant_sku: str, request: Request) -> dict[str, object]:
        """List media assets linked to the product of this variant."""
        from factory_os.domain.media import media_thumb_url

        require_human(request)
        shop_rt = runtime()
        tenant = tenant_id()
        record = shop_rt.store.get_variant(tenant, variant_sku)
        if record is None:
            raise HTTPException(status_code=404, detail="unknown_variant")
        links = shop_rt.store.list_product_media(tenant, record.product_sku)
        media_rows: list[dict[str, object]] = []
        for link in links:
            asset = shop_rt.store.get_media_asset(tenant, link.asset_id)
            if asset is None:
                continue
            media_rows.append(
                {
                    "asset_id": str(asset.id),
                    "is_primary": link.is_primary,
                    "sort_order": link.sort_order,
                    "mime": asset.mime,
                    "thumb_url": media_thumb_url(asset.id),
                    "image_path": asset.storage_key,
                    "thumb_path": asset.thumb_key or "",
                }
            )
        return {"variant_sku": variant_sku, "product_sku": record.product_sku, "media": media_rows}

    @app.get("/api/media/{asset_id}")
    def get_media_asset(asset_id: str, request: Request, variant: str = "original") -> Response:
        """Serve original or thumb bytes. Panel auth required (ADR-015)."""
        from factory_os.domain.media import (
            media_cache_headers,
            media_etag_matches,
            read_media_bytes,
        )

        require_human(request)
        try:
            mid = UUID(asset_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="unknown_media") from exc
        shop_rt = runtime()
        tenant = tenant_id()
        asset = shop_rt.store.get_media_asset(tenant, mid)
        if asset is None:
            raise HTTPException(status_code=404, detail="unknown_media")
        choice = (variant or "original").strip().lower()
        if choice == "thumb":
            key = asset.thumb_key or asset.storage_key
            content_type = "image/jpeg" if asset.thumb_key else asset.mime
        elif choice in {"original", "full"}:
            key = asset.storage_key
            content_type = asset.mime
        else:
            raise HTTPException(status_code=400, detail="bad_variant")
        headers = media_cache_headers(
            variant=choice,
            asset_id=asset.id,
            size_bytes=int(asset.size_bytes),
        )
        if media_etag_matches(request.headers.get("if-none-match"), headers["ETag"]):
            return Response(status_code=304, headers=headers)
        try:
            data = read_media_bytes(key)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="unknown_media") from exc
        return Response(content=data, media_type=content_type, headers=headers)

    @app.post("/api/catalog/{variant_sku}/availability")
    def set_catalog_availability(
        variant_sku: str, body: CatalogAvailabilityIn, request: Request
    ) -> dict[str, object]:
        require_human(request)
        shop_rt = runtime()
        try:
            record = shop_rt.store.set_variant_availability(
                tenant_id(),
                variant_sku,
                available=body.available,
                stock=body.stock,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="variant_not_found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="bad_stock") from exc
        return {
            "variant_sku": record.variant_sku,
            "available": not bool(record.attributes.get("disabled")),
            "stock": record.stock,
        }

    def _cash_http_error(exc: ValueError) -> HTTPException:
        code = str(exc)
        if code in {
            "session_required",
            "session_open",
            "already_voided",
            "out_of_stock",
            "disabled_variant",
        }:
            return HTTPException(status_code=409, detail=code)
        if code in {"movement_not_found", "ticket_not_found"}:
            return HTTPException(status_code=404, detail=code)
        if code in {
            "note_required",
            "reason_required",
            "void_reason_required",
            "empty",
            "empty_file",
            "file_too_large",
            "bad_quantity",
            "unknown_variant",
            "bad_method",
        }:
            return HTTPException(status_code=400, detail=code)
        if code in {"bad_amount", "bad_direction"}:
            return HTTPException(status_code=400, detail=code)
        return HTTPException(status_code=400, detail="bad_cash")

    @app.get("/api/cash/session")
    def get_cash_session(request: Request) -> dict[str, object]:
        require_human(request)
        from factory_os.domain.cash_drawer import session_payload

        shop_rt = runtime()
        session = shop_rt.store.get_open_cash_session(tenant_id())
        if session is None:
            return {"session": None}
        return {"session": session_payload(shop_rt.store, session)}

    @app.post("/api/cash/session/open")
    def open_cash_session(body: CashSessionOpenIn, request: Request) -> dict[str, object]:
        actor = require_human(request)
        from factory_os.domain.cash_drawer import open_session, parse_money, session_payload

        shop_rt = runtime()
        try:
            opening = parse_money(body.opening_float)
            session = open_session(
                shop_rt.store,
                tenant_id(),
                opening,
                (body.currency or "BOB").strip() or "BOB",
                actor.name,
                actor.user_id,
            )
        except ValueError as exc:
            raise _cash_http_error(exc) from exc
        return session_payload(shop_rt.store, session)

    @app.post("/api/cash/session/close")
    def close_cash_session(body: CashSessionCloseIn, request: Request) -> dict[str, object]:
        actor = require_supervisor(request)
        from factory_os.domain.cash_drawer import close_session, parse_money, session_payload

        shop_rt = runtime()
        try:
            counted = parse_money(body.counted_cash)
            session = close_session(
                shop_rt.store,
                tenant_id(),
                counted,
                body.note or "",
                actor.name,
                actor.user_id,
            )
        except ValueError as exc:
            raise _cash_http_error(exc) from exc
        return session_payload(shop_rt.store, session)

    @app.post("/api/cash/session/reopen")
    def reopen_cash_session_endpoint(
        body: CashSessionReopenIn, request: Request
    ) -> dict[str, object]:
        actor = require_supervisor(request)
        tenant = tenant_id()
        _require_pin_if_configured(actor, body.pin, tenant=tenant)
        from factory_os.domain.cash_drawer import reopen_session, session_payload

        shop_rt = runtime()
        try:
            session = reopen_session(shop_rt.store, tenant, actor.name, actor.user_id)
        except ValueError as exc:
            raise _cash_http_error(exc) from exc
        return session_payload(shop_rt.store, session)

    @app.get("/api/cash/session/history")
    def cash_session_history(request: Request) -> dict[str, object]:
        require_human(request)
        from factory_os.domain.cash_drawer import session_payload

        shop_rt = runtime()
        closes = shop_rt.store.list_cash_sessions(tenant_id(), status="closed")
        return {"closes": [session_payload(shop_rt.store, item) for item in closes]}

    @app.get("/api/cash/catalog")
    def cash_catalog(request: Request, q: str = "") -> dict[str, object]:
        """Walk-in drawer catalog search by code, description, or price."""
        require_human(request)
        from factory_os.domain.cash_sales import search_cash_catalog

        shop_rt = runtime()
        hits = search_cash_catalog(shop_rt.store, tenant_id(), q or "")
        return {"hits": hits}

    @app.get("/api/cash/grid")
    def cash_grid(request: Request, q: str = "", category: str = "") -> dict[str, object]:
        """Product grid for the counter. Sold-out stays visible. Price comes from the catalog."""
        require_human(request)
        from factory_os.domain.cash_grid import build_cash_grid

        shop_rt = runtime()
        return {
            "products": build_cash_grid(
                shop_rt.store, tenant_id(), query=q or "", category=category or ""
            )
        }

    @app.post("/api/cash/sales")
    def post_cash_sale(body: CashSaleIn, request: Request) -> dict[str, object]:
        actor = _sale_actor(request, body.discount_amount, body.pin)
        from factory_os.domain.cash_sales import CashSaleError, create_walkin_sale, ticket_payload

        shop_rt = runtime()
        try:
            ticket = create_walkin_sale(
                shop_rt.store,
                tenant_id(),
                method=(body.method or "cash").strip() or "cash",
                lines=_requested_sale_lines(body.lines),
                recorded_by_name=actor.name,
                recorded_by_id=actor.user_id,
                discount_amount=body.discount_amount,
            )
        except CashSaleError as exc:
            raise HTTPException(status_code=exc.status, detail=exc.code) from exc
        except ValueError as exc:
            raise _cash_http_error(exc) from exc
        return ticket_payload(ticket)

    @app.get("/api/cash/tabs")
    def list_cash_tabs(request: Request) -> dict[str, object]:
        require_human(request)
        from factory_os.domain.cash_sales import list_open_counter_tabs, tab_payload

        shop_rt = runtime()
        tabs = list_open_counter_tabs(shop_rt.store, tenant_id())
        return {"tabs": [tab_payload(order) for order in tabs]}

    @app.post("/api/cash/tabs")
    def post_cash_tab(body: CashTabIn, request: Request) -> dict[str, object]:
        require_human(request)
        from factory_os.domain.cash_sales import CashSaleError, open_counter_tab, tab_payload

        shop_rt = runtime()
        try:
            order = open_counter_tab(
                shop_rt.store,
                tenant_id(),
                table=body.table,
                lines=_requested_sale_lines(body.lines),
            )
        except CashSaleError as exc:
            raise HTTPException(status_code=exc.status, detail=exc.code) from exc
        except ValueError as exc:
            raise _cash_http_error(exc) from exc
        return tab_payload(order)

    @app.post("/api/cash/tabs/{order_id}/cancel")
    def cancel_cash_tab(order_id: UUID, request: Request) -> dict[str, object]:
        require_human(request)
        from factory_os.domain.cash_sales import CashSaleError, cancel_counter_tab, tab_payload

        shop_rt = runtime()
        try:
            order = cancel_counter_tab(shop_rt.store, tenant_id(), order_id)
        except CashSaleError as exc:
            raise HTTPException(status_code=exc.status, detail=exc.code) from exc
        except ValueError as exc:
            raise _cash_http_error(exc) from exc
        return tab_payload(order)

    @app.post("/api/cash/tabs/{order_id}/charge")
    def charge_cash_tab(
        order_id: UUID, body: CashTabChargeIn, request: Request
    ) -> dict[str, object]:
        actor = _sale_actor(request, body.discount_amount, body.pin)
        from factory_os.domain.cash_sales import CashSaleError, charge_counter_tab, ticket_payload

        shop_rt = runtime()
        try:
            ticket = charge_counter_tab(
                shop_rt.store,
                tenant_id(),
                order_id,
                method=(body.method or "cash").strip() or "cash",
                recorded_by_name=actor.name,
                recorded_by_id=actor.user_id,
                discount_amount=body.discount_amount,
            )
        except CashSaleError as exc:
            raise HTTPException(status_code=exc.status, detail=exc.code) from exc
        except ValueError as exc:
            raise _cash_http_error(exc) from exc
        return ticket_payload(ticket)

    @app.post("/api/cash/sales/qr")
    def post_cash_sale_qr(body: CashSaleIn, request: Request) -> dict[str, object]:
        """Walk-in QR: pending ticket + payment QR; stock/drawer wait for adapter confirm."""
        actor = _sale_actor(request, body.discount_amount, body.pin)
        from factory_os.domain.cash_sales import (
            CashSaleError,
            create_walkin_qr_sale,
            ticket_payload,
        )

        shop_rt = runtime()
        try:
            ticket, qr = create_walkin_qr_sale(
                shop_rt.store,
                shop_rt.payments,
                tenant_id(),
                lines=_requested_sale_lines(body.lines),
                recorded_by_name=actor.name,
                recorded_by_id=actor.user_id,
                discount_amount=body.discount_amount,
            )
        except CashSaleError as exc:
            raise HTTPException(status_code=exc.status, detail=exc.code) from exc
        except ValueError as exc:
            raise _cash_http_error(exc) from exc
        return ticket_payload(ticket, qr=qr)

    @app.post("/api/cash/sales/{sale_id}/cancel")
    def cancel_cash_sale_qr(sale_id: str, request: Request) -> dict[str, object]:
        """Cancel unpaid pending walk-in QR (staff OK). Releases hold; no recorded void."""
        require_human(request)
        from factory_os.domain.cash_sales import CashSaleError, cancel_walkin_qr_pending, ticket_payload

        try:
            tid = UUID(sale_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="ticket_not_found") from exc
        shop_rt = runtime()
        try:
            ticket = cancel_walkin_qr_pending(shop_rt.store, tenant_id(), tid)
        except CashSaleError as exc:
            raise HTTPException(status_code=exc.status, detail=exc.code) from exc
        except ValueError as exc:
            raise _cash_http_error(exc) from exc
        return ticket_payload(ticket)

    @app.post("/api/cash/sales/{sale_id}/check")
    def check_cash_sale_qr(sale_id: str, request: Request) -> dict[str, object]:
        """Poll provider status for a pending walk-in QR; confirm when the bank says so."""
        require_human(request)
        from factory_os.domain.cash_sales import ticket_payload
        from factory_os.domain.models import PaymentStatus

        try:
            tid = UUID(sale_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="ticket_not_found") from exc
        shop_rt = runtime()
        ticket = shop_rt.store.get_cash_sale_ticket(tenant_id(), tid)
        if ticket is None:
            raise HTTPException(status_code=404, detail="ticket_not_found")
        if ticket.status == "pending_qr" and ticket.provider_ref:
            state = shop_rt.payments.status(ticket.provider_ref)
            if state is PaymentStatus.CONFIRMED:
                shop_rt.confirm_payment_from_adapter(ticket.provider_ref)
                ticket = shop_rt.store.get_cash_sale_ticket(tenant_id(), tid) or ticket
        qr: str | None = None
        if ticket.payment_id is not None:
            payment = shop_rt.store.get_payment(tenant_id(), ticket.payment_id)
            if payment is not None:
                qr = payment.qr_payload or None
        return ticket_payload(ticket, qr=qr)

    @app.get("/api/cash/sales/{sale_id}")
    def get_cash_sale(sale_id: str, request: Request) -> dict[str, object]:
        require_human(request)
        from factory_os.domain.cash_sales import ticket_payload

        try:
            tid = UUID(sale_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="ticket_not_found") from exc
        shop_rt = runtime()
        ticket = shop_rt.store.get_cash_sale_ticket(tenant_id(), tid)
        if ticket is None:
            raise HTTPException(status_code=404, detail="ticket_not_found")
        qr: str | None = None
        if ticket.payment_id is not None:
            payment = shop_rt.store.get_payment(tenant_id(), ticket.payment_id)
            if payment is not None:
                qr = payment.qr_payload or None
        return ticket_payload(ticket, qr=qr)

    def _cash_list_scoped(session_id: UUID | None = None):
        from factory_os.domain.cash_activity import resolve_cash_session_scope

        shop_rt = runtime()
        tenant = tenant_id()
        session_row = resolve_cash_session_scope(shop_rt.store, tenant, session_id=session_id)
        if session_row is None:
            return shop_rt, None, []
        movements = shop_rt.store.list_cash(tenant, session_id=session_row.id)
        return shop_rt, session_row, movements

    def _enrich_activity_line_attrs(
        store: object, tenant: UUID, payload: dict[str, object]
    ) -> dict[str, object]:
        """Fill talla/color on detail lines from catalog variant attrs when missing."""
        lines = payload.get("lines")
        if not isinstance(lines, list) or not lines:
            return payload
        get_variant = getattr(store, "get_variant", None)
        if not callable(get_variant):
            return payload
        enriched: list[object] = []
        for raw in lines:
            if not isinstance(raw, dict):
                enriched.append(raw)
                continue
            row = dict(raw)
            sku = str(row.get("variant_sku") or "").strip()
            if sku and (not row.get("talla") or not row.get("color")):
                record = get_variant(tenant, sku)
                attrs = getattr(record, "attributes", None) if record is not None else None
                if isinstance(attrs, dict):
                    if not row.get("talla") and attrs.get("talla") not in (None, ""):
                        row["talla"] = str(attrs.get("talla"))
                    if not row.get("color") and attrs.get("color") not in (None, ""):
                        row["color"] = str(attrs.get("color"))
            enriched.append(row)
        payload["lines"] = enriched
        return payload

    def _cash_filter_kwargs(
        *,
        direction: str | None,
        category: str | None,
        method: str | None,
        status: str | None,
        user: str | None,
        from_date: str | None,
        to_date: str | None,
    ) -> dict[str, str | None]:
        return {
            "direction": direction,
            "category": category,
            "method": method,
            "status": status,
            "user": user,
            "from_date": from_date,
            "to_date": to_date,
        }

    @app.get("/api/cash")
    def get_cash(
        request: Request,
        direction: str | None = None,
        category: str | None = None,
        method: str | None = None,
        status: str | None = None,
        user: str | None = None,
        from_date: str | None = Query(None, alias="from"),
        to_date: str | None = Query(None, alias="to"),
        session_id: str | None = None,
    ) -> dict[str, object]:
        """Cash drawer book + unified session activity feed (QR informative)."""
        require_human(request)
        from factory_os.domain.cash_activity import build_session_entries, filter_activity_entries
        from factory_os.domain.cash_drawer import (
            filter_movements,
            movement_payload,
            session_payload,
            sum_session_cash,
        )

        scoped_session_id: UUID | None = None
        if session_id and session_id.strip():
            try:
                scoped_session_id = UUID(session_id.strip())
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="bad_session_id") from exc

        shop_rt, session_row, movements = _cash_list_scoped(scoped_session_id)
        incoming, outgoing = sum_session_cash(movements)
        filter_kwargs = _cash_filter_kwargs(
            direction=direction,
            category=category,
            method=method,
            status=status,
            user=user,
            from_date=from_date,
            to_date=to_date,
        )
        filtered = filter_movements(movements, **filter_kwargs)
        tickets = (
            shop_rt.store.list_cash_sale_tickets(tenant_id(), session_id=session_row.id)
            if session_row is not None
            else []
        )
        entries = filter_activity_entries(
            build_session_entries(movements, tickets),
            **filter_kwargs,
        )
        return {
            "in": str(incoming),
            "out": str(outgoing),
            "balance": str(incoming - outgoing),
            "count": len(filtered),
            "session": session_payload(shop_rt.store, session_row) if session_row else None,
            "note": (
                "Caja interna. Los QR de clientes los confirma Cobros; "
                "en Movimientos aparecen informativos y no mueven el efectivo."
            ),
            "movements": [movement_payload(item) for item in reversed(filtered)],
            "entries": entries,
        }

    @app.post("/api/cash")
    def post_cash(body: CashIn, request: Request) -> dict[str, object]:
        actor = require_human(request)
        from factory_os.domain.cash_drawer import movement_payload

        direction = body.direction.strip().lower()
        if direction not in {"in", "out"}:
            raise HTTPException(status_code=400, detail="bad_direction")
        reason = (body.reason or "").strip()
        if direction == "out" and not reason:
            raise HTTPException(status_code=400, detail="reason_required")
        try:
            amount = Decimal(body.amount.strip().replace(",", "."))
        except (InvalidOperation, AttributeError) as exc:
            raise HTTPException(status_code=400, detail="bad_amount") from exc
        if amount <= 0:
            raise HTTPException(status_code=400, detail="bad_amount")
        shop_rt = runtime()
        try:
            movement = shop_rt.store.record_cash(
                tenant_id(),
                direction,
                amount,
                (body.currency or "BOB").strip() or "BOB",
                reason or ("entrada" if direction == "in" else "salida"),
                category=(body.category or "").strip(),
                method=(body.method or "cash").strip() or "cash",
                recorded_by_name=actor.name,
                recorded_by_id=actor.user_id,
            )
        except ValueError as exc:
            raise _cash_http_error(exc) from exc
        return movement_payload(movement)

    @app.get("/api/cash/export")
    def export_cash(
        request: Request,
        export_format: str | None = Query(None, alias="format"),
        direction: str | None = None,
        category: str | None = None,
        method: str | None = None,
        status: str | None = None,
        user: str | None = None,
        from_date: str | None = Query(None, alias="from"),
        to_date: str | None = Query(None, alias="to"),
    ) -> Response:
        """Export filtered cash movements as CSV or a minimal PDF."""
        require_human(request)
        from factory_os.domain.cash_drawer import filter_movements, movements_to_csv, movements_to_pdf

        kind = (export_format or "").strip().lower()
        if kind not in {"csv", "pdf"}:
            raise HTTPException(status_code=400, detail="bad_format")
        _shop_rt, _open_session_row, movements = _cash_list_scoped()
        filtered = filter_movements(
            movements,
            **_cash_filter_kwargs(
                direction=direction,
                category=category,
                method=method,
                status=status,
                user=user,
                from_date=from_date,
                to_date=to_date,
            ),
        )
        # Newest first, same order as the list endpoint.
        ordered = list(reversed(filtered))
        if kind == "csv":
            body = movements_to_csv(ordered)
            return Response(
                content=body,
                media_type="text/csv; charset=utf-8",
                headers={"Content-Disposition": 'attachment; filename="cash_export.csv"'},
            )
        pdf_bytes = movements_to_pdf(ordered)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="cash_export.pdf"'},
        )

    @app.get("/api/cash/activity/{entry_id}")
    def get_cash_activity_detail(
        entry_id: str,
        request: Request,
        kind: str | None = None,
    ) -> dict[str, object]:
        """Stable detail for a Movimientos row (cash movement or informative QR sale)."""
        require_human(request)
        from factory_os.domain.cash_activity import activity_detail_payload
        from factory_os.domain.cash_attachments import attachment_payload

        try:
            eid = UUID(entry_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="activity_not_found") from exc

        kind_norm = (kind or "").strip().lower() or None
        if kind_norm is not None and kind_norm not in {"cash_movement", "qr_sale"}:
            raise HTTPException(status_code=400, detail="bad_activity_kind")

        shop_rt = runtime()
        tenant = tenant_id()
        store = shop_rt.store

        movement = None
        ticket = None
        if kind_norm in (None, "cash_movement"):
            movement = store.get_cash_movement(tenant, eid)
        if kind_norm in (None, "qr_sale") and movement is None:
            ticket = store.get_cash_sale_ticket(tenant, eid)

        if movement is not None:
            resolved_ticket = None
            if movement.ticket_id is not None:
                resolved_ticket = store.get_cash_sale_ticket(tenant, movement.ticket_id)
            if resolved_ticket is None:
                for candidate in store.list_cash_sale_tickets(tenant, session_id=movement.session_id):
                    if candidate.movement_id == movement.id:
                        resolved_ticket = candidate
                        break
            rows = store.list_cash_attachments(tenant, movement.id)
            payload = activity_detail_payload(
                kind="cash_movement",
                movement=movement,
                ticket=resolved_ticket,
                attachments=[attachment_payload(item) for item in rows],
            )
            return _enrich_activity_line_attrs(store, tenant, payload)

        if ticket is not None and (ticket.method or "").strip().lower() == "qr":
            payload = activity_detail_payload(kind="qr_sale", ticket=ticket)
            return _enrich_activity_line_attrs(store, tenant, payload)

        raise HTTPException(status_code=404, detail="activity_not_found")

    @app.get("/api/cash/activity/{entry_id}/ticket.pdf")
    def get_cash_activity_ticket_pdf(
        entry_id: str,
        request: Request,
        kind: str | None = None,
    ) -> Response:
        """Narrow thermal-style sale receipt PDF for walk-in cash/QR tickets."""
        require_human(request)
        from factory_os.domain.cash_activity import activity_detail_payload
        from factory_os.domain.cash_attachments import attachment_payload
        from factory_os.domain.cash_ticket_pdf import sale_ticket_to_pdf

        try:
            eid = UUID(entry_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="ticket_not_found") from exc

        kind_norm = (kind or "").strip().lower() or None
        if kind_norm is not None and kind_norm not in {"cash_movement", "qr_sale"}:
            raise HTTPException(status_code=400, detail="bad_activity_kind")

        shop_rt = runtime()
        tenant = tenant_id()
        store = shop_rt.store

        movement = None
        ticket = None
        if kind_norm in (None, "cash_movement"):
            movement = store.get_cash_movement(tenant, eid)
        if kind_norm in (None, "qr_sale") and movement is None:
            ticket = store.get_cash_sale_ticket(tenant, eid)

        payload: dict[str, object] | None = None
        if movement is not None:
            resolved_ticket = None
            if movement.ticket_id is not None:
                resolved_ticket = store.get_cash_sale_ticket(tenant, movement.ticket_id)
            if resolved_ticket is None:
                for candidate in store.list_cash_sale_tickets(tenant, session_id=movement.session_id):
                    if candidate.movement_id == movement.id:
                        resolved_ticket = candidate
                        break
            if resolved_ticket is None or not resolved_ticket.lines:
                raise HTTPException(status_code=404, detail="ticket_not_found")
            rows = store.list_cash_attachments(tenant, movement.id)
            payload = _enrich_activity_line_attrs(
                store,
                tenant,
                activity_detail_payload(
                    kind="cash_movement",
                    movement=movement,
                    ticket=resolved_ticket,
                    attachments=[attachment_payload(item) for item in rows],
                ),
            )
        elif ticket is not None and (ticket.method or "").strip().lower() == "qr":
            if not ticket.lines and not ticket.number:
                raise HTTPException(status_code=404, detail="ticket_not_found")
            payload = _enrich_activity_line_attrs(
                store,
                tenant,
                activity_detail_payload(kind="qr_sale", ticket=ticket),
            )
        else:
            raise HTTPException(status_code=404, detail="ticket_not_found")

        ticket_number = str(payload.get("ticket_number") or "").strip()
        lines = payload.get("lines")
        has_lines = isinstance(lines, list) and len(lines) > 0
        if not ticket_number or not has_lines:
            raise HTTPException(status_code=404, detail="ticket_not_found")

        pdf_bytes = sale_ticket_to_pdf(payload)
        safe_name = "".join(
            ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in ticket_number
        ) or "ticket"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="ticket-{safe_name}.pdf"',
            },
        )

    @app.get("/api/cash/{movement_id}/attachments")
    def list_cash_attachments(movement_id: str, request: Request) -> dict[str, object]:
        """List attachment metadata for a cash movement (bytes stay on disk)."""
        require_human(request)
        from factory_os.domain.cash_attachments import attachment_payload

        try:
            mid = UUID(movement_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="movement_not_found") from exc
        shop_rt = runtime()
        tenant = tenant_id()
        if shop_rt.store.get_cash_movement(tenant, mid) is None:
            raise HTTPException(status_code=404, detail="movement_not_found")
        rows = shop_rt.store.list_cash_attachments(tenant, mid)
        return {"attachments": [attachment_payload(item) for item in rows]}

    @app.post("/api/cash/{movement_id}/attachments")
    async def upload_cash_attachment(movement_id: str, request: Request) -> dict[str, object]:
        """Store file bytes on disk; persist metadata only in the store."""
        from datetime import UTC, datetime
        from uuid import uuid4

        from factory_os.domain.cash_attachments import (
            MAX_ATTACHMENT_BYTES,
            attachment_payload,
            build_storage_key,
            cash_attachments_root,
            write_attachment_bytes,
        )
        from factory_os.domain.models import CashAttachment

        actor = require_human(request)
        try:
            mid = UUID(movement_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="movement_not_found") from exc
        shop_rt = runtime()
        tenant = tenant_id()
        if shop_rt.store.get_cash_movement(tenant, mid) is None:
            raise HTTPException(status_code=404, detail="movement_not_found")
        content_type_header = request.headers.get("content-type", "")
        media = content_type_header.split(";", 1)[0].strip().lower()
        if not media.startswith("multipart/"):
            raise HTTPException(status_code=400, detail="empty_file")
        try:
            fields = _multipart_fields(await request.body(), content_type_header)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="empty_file") from exc
        upload: tuple[str | None, str, bytes] | None = None
        for name, upload_name, part_type, data in fields:
            if name == "file" and upload is None:
                upload = (upload_name, part_type, data)
        if upload is None:
            raise HTTPException(status_code=400, detail="empty_file")
        upload_name, part_type, data = upload
        if not data:
            raise HTTPException(status_code=400, detail="empty_file")
        if len(data) > MAX_ATTACHMENT_BYTES:
            raise HTTPException(status_code=400, detail="file_too_large")
        filename = (upload_name or "file").strip() or "file"
        content_type = (part_type or "application/octet-stream").strip() or (
            "application/octet-stream"
        )
        storage_key = build_storage_key(tenant, mid, filename)
        write_attachment_bytes(storage_key, data, root=cash_attachments_root())
        attachment = CashAttachment(
            id=uuid4(),
            tenant_id=tenant,
            movement_id=mid,
            filename=filename,
            content_type=content_type,
            size_bytes=len(data),
            storage_key=storage_key,
            uploaded_by_name=actor.name,
            created_at=datetime.now(UTC),
        )
        try:
            saved = shop_rt.store.add_cash_attachment(tenant, attachment)
        except ValueError as exc:
            raise _cash_http_error(exc) from exc
        return attachment_payload(saved)

    @app.post("/api/cash/{movement_id}/void")
    def void_cash_movement(movement_id: str, body: CashVoidIn, request: Request) -> dict[str, object]:
        actor = require_supervisor(request)
        tenant = tenant_id()
        _require_pin_if_configured(actor, body.pin, tenant=tenant)
        from factory_os.domain.cash_drawer import movement_payload

        reason = (body.reason or "").strip()
        if not reason:
            raise HTTPException(status_code=400, detail="void_reason_required")
        try:
            mid = UUID(movement_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="movement_not_found") from exc
        shop_rt = runtime()
        try:
            movement = shop_rt.store.void_cash(
                tenant,
                mid,
                reason,
                actor.name,
                actor.user_id,
            )
        except ValueError as exc:
            raise _cash_http_error(exc) from exc
        return movement_payload(movement)

    @app.get("/api/knowledge")
    def get_knowledge(request: Request) -> dict[str, object]:
        """Ficha del negocio. No incluye precio, stock ni confirmación de pago."""
        require_human(request)
        from factory_os.domain.knowledge import load_shop_pack, sanitize_shop_pack

        shop_rt = runtime()
        stored = shop_rt.store.get_shop_knowledge(tenant_id())
        pack = sanitize_shop_pack(stored if stored is not None else load_shop_pack())
        return pack

    @app.put("/api/knowledge")
    async def put_knowledge(request: Request) -> dict[str, object]:
        require_owner(request)
        from factory_os.domain.knowledge import load_shop_pack, merge_shop_pack, sanitize_shop_pack

        raw = await request.json()
        if not isinstance(raw, dict):
            raise HTTPException(status_code=400, detail="bad_knowledge")
        shop_rt = runtime()
        current = shop_rt.store.get_shop_knowledge(tenant_id())
        base = current if current is not None else load_shop_pack()
        stored = shop_rt.store.put_shop_knowledge(tenant_id(), merge_shop_pack(base, raw))
        return sanitize_shop_pack(stored)

    @app.post("/api/knowledge/propose")
    async def post_knowledge_propose(request: Request) -> dict[str, object]:
        """Propose a shop pack from plain text. Does not write shop_knowledge."""
        require_owner(request)
        from factory_os.domain.knowledge_ingest import propose_shop_pack_from_text

        filename, kind, text = await _propose_inputs(request)
        used = text.replace("\x00", "")
        if len(used) > 50_000:
            used = used[:50_000]
        if not used.strip():
            raise HTTPException(status_code=400, detail="bad_body")
        return {
            "proposal": propose_shop_pack_from_text(used, kind=kind),
            "source": {"filename": filename, "chars": len(used)},
            "wrote": False,
        }

    @app.get("/api/customers")
    def list_customers(request: Request) -> dict[str, object]:
        require_human(request)
        shop_rt = runtime()
        tenant = tenant_id()
        orders = shop_rt.store.list_orders(tenant)
        conversations = shop_rt.store.list_conversations(tenant)
        rows = []
        for customer in shop_rt.store.list_customers(tenant):
            if str(customer.wa_number or "").startswith("internal:"):
                continue
            rows.append(
                {
                    "id": str(customer.id),
                    "name": customer.name,
                    "wa_number": customer.wa_number,
                    "address": customer.address,
                    "order_count": sum(
                        1
                        for order in orders
                        if order.customer_id == customer.id
                        and getattr(order, "origin", "agent") != "counter"
                    ),
                    "note_count": len(shop_rt.store.list_customer_notes(tenant, customer.id)),
                    "conversation_count": sum(
                        1 for conv in conversations if conv.customer_id == customer.id
                    ),
                }
            )
        return {"customers": rows}

    @app.get("/api/customers/{customer_id}")
    def get_customer_file(customer_id: str, request: Request) -> dict[str, object]:
        require_human(request)
        shop_rt = runtime()
        tenant = tenant_id()
        try:
            customer = shop_rt.store.get_customer(tenant, UUID(customer_id))
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="customer") from exc
        if customer is None:
            raise HTTPException(status_code=404, detail="customer")
        customer = _hydrate_customer_from_latest_delivery(shop_rt.store, tenant, customer)
        orders = [
            _customer_order_view(shop_rt.store, tenant, order)
            for order in shop_rt.store.list_orders(tenant)
            if order.customer_id == customer.id
        ]
        conversations = []
        for conv in shop_rt.store.list_conversations(tenant):
            if conv.customer_id != customer.id:
                continue
            last = conv.messages[-1][1] if conv.messages else ""
            conversations.append(
                {
                    "id": str(conv.id),
                    "message_count": len(conv.messages),
                    "last_text": last,
                    "human_takeover": conv.state.human_takeover,
                    "needs_human": conv.state.needs_human,
                    "cart": _cart_view(conv.state.cart),
                }
            )
        notes = [
            {
                "id": str(note.id),
                "body": note.body,
                "created_at": note.created_at.isoformat() if note.created_at else None,
            }
            for note in shop_rt.store.list_customer_notes(tenant, customer.id)
        ]
        return {
            "id": str(customer.id),
            "name": customer.name,
            "wa_number": customer.wa_number,
            "address": customer.address,
            "preferences": shop_rt.store.get_customer_preferences(tenant, customer.id),
            "orders": orders,
            "conversations": conversations,
            "notes": notes,
        }

    @app.post("/api/customers/{customer_id}/notes")
    def post_customer_note(customer_id: str, body: NoteIn, request: Request) -> dict[str, object]:
        require_human(request)
        shop_rt = runtime()
        tenant = tenant_id()
        try:
            note = shop_rt.store.add_customer_note(tenant, UUID(customer_id), body.body)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="empty_note") from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="customer") from exc
        return {
            "id": str(note.id),
            "body": note.body,
            "created_at": note.created_at.isoformat() if note.created_at else None,
        }

    @app.get("/api/metrics")
    def get_metrics(
        request: Request,
        period: str = "7d",
        date_from: str | None = None,
        date_to: str | None = None,
        now: str | None = None,
    ) -> dict[str, object]:
        """Analítica: hechos del período. Owner y supervisor. Staff no entra."""
        require_supervisor(request)
        from factory_os.domain.analytics import build_analytics_summary, parse_instant

        try:
            summary = build_analytics_summary(
                runtime().store,
                tenant_id(),
                period=period,
                now=parse_instant(now),
                date_from=parse_instant(date_from),
                date_to=parse_instant(date_to),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="bad_period") from exc
        return summary

    @app.get("/api/analytics/thresholds")
    def get_analytics_thresholds(request: Request) -> dict[str, object]:
        actor = require_supervisor(request)
        shop_rt = runtime()
        thresholds = shop_rt.store.get_analytics_thresholds(tenant_id())
        return _thresholds_payload(
            thresholds,
            can_edit=actor.role == "owner",
            owner_numbers=shop_rt.owner_numbers,
        )

    @app.patch("/api/analytics/thresholds")
    def patch_analytics_thresholds(
        body: AnalyticsThresholdsIn, request: Request
    ) -> dict[str, object]:
        require_owner(request)
        from factory_os.domain.analytics_thresholds import merge_thresholds

        shop_rt = runtime()
        tenant = tenant_id()
        current = shop_rt.store.get_analytics_thresholds(tenant)
        try:
            updated = merge_thresholds(current, body.model_dump(exclude_unset=True))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        saved = shop_rt.store.put_analytics_thresholds(tenant, updated)
        return _thresholds_payload(
            saved,
            can_edit=True,
            owner_numbers=shop_rt.owner_numbers,
        )

    @app.post("/api/rules/run")
    def post_rules_run(request: Request) -> dict[str, object]:
        """Evaluate published catalog rules for this shop (cron or operator)."""
        require_supervisor(request)
        from factory_os.domain.rule_runtime import run_published_rules

        shop_rt = runtime()
        results = run_published_rules(
            shop_rt.store,
            tenant_id(),
            url=_database_url(),
            channel=shop_rt.channel,
            owner_numbers=shop_rt.owner_numbers,
        )
        return {"fired": len(results), "results": results}

    @app.post("/api/analytics/digest/run")
    def post_analytics_digest(
        request: Request,
        body: AnalyticsDigestRunIn | None = None,
    ) -> dict[str, object]:
        """Digest. Cron calls without force (supervisor). Manual send uses force (owner)."""
        from datetime import UTC, datetime

        from factory_os.domain.analytics_digest import run_owner_analytics_digest

        payload = body or AnalyticsDigestRunIn()
        if payload.force:
            require_owner(request)
        else:
            require_supervisor(request)
        shop_rt = runtime()
        moment = datetime.now(UTC)
        if payload.dry_run:
            return _analytics_digest_preview(
                shop_rt.store,
                tenant_id(),
                now=moment,
                force=payload.force,
            )
        return run_owner_analytics_digest(
            shop_rt.store,
            tenant_id(),
            shop_rt.channel,
            shop_rt.owner_numbers,
            now=moment,
            force=payload.force,
        )

    @app.post("/api/analytics/ask")
    def post_analytics_ask(body: AnalyticsAskIn, request: Request) -> dict[str, object]:
        """Supervisor narrative over the analytics summary. One model call, or the fallback."""
        require_supervisor(request)
        question = body.question.strip()
        if not question:
            raise HTTPException(status_code=400, detail="empty_question")
        from factory_os.domain.analytics_ask import answer_analytics_question

        shop_rt = runtime()
        try:
            answered = answer_analytics_question(
                shop_rt.store,
                tenant_id(),
                question,
                shop_rt.gateway,
                period=body.period or "7d",
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"reply": answered["reply"], "used_fallback": answered["used_fallback"]}

    @app.get("/api/alerts")
    def get_alerts(request: Request) -> dict[str, object]:
        require_human(request)
        from datetime import UTC, datetime

        from factory_os.domain.reports import alert_payload

        return alert_payload(runtime().store, tenant_id(), datetime.now(UTC))

    @app.get("/api/reports/catalog")
    def get_report_catalog(
        request: Request,
        period: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> dict[str, object]:
        require_supervisor(request)
        from factory_os.domain.reports import report_catalog

        try:
            return report_catalog(
                runtime().store,
                tenant_id(),
                period=period,
                date_from=date_from,
                date_to=date_to,
            )
        except ValueError as exc:
            detail = str(exc) or "bad_period"
            status = 404 if detail == "unknown_report" else 400
            raise HTTPException(status_code=status, detail=detail) from exc

    @app.get("/api/reports/downloads/history")
    def get_report_download_history(request: Request) -> dict[str, object]:
        require_supervisor(request)
        from factory_os.domain.reports import download_public

        rows = runtime().store.list_report_downloads(tenant_id())
        return {"downloads": [download_public(row) for row in rows]}

    @app.get("/api/reports/package")
    def get_report_package(
        request: Request,
        period: str | None = None,
        month: str | None = None,
        export_format: str | None = Query(None, alias="format"),
    ) -> Response:
        actor = require_supervisor(request)
        from datetime import UTC, datetime

        from factory_os.domain.reports import (
            build_package_files,
            excel_available,
            package_xlsx,
            package_zip,
        )

        fmt = (export_format or ("xlsx" if excel_available() else "zip")).strip().lower()
        if fmt == "xlsx" and not excel_available():
            raise HTTPException(status_code=501, detail="excel_unavailable")
        if fmt not in {"zip", "xlsx"}:
            raise HTTPException(status_code=400, detail="bad_format")
        try:
            label, start, end, files = build_package_files(
                runtime().store,
                tenant_id(),
                month=month,
                period=period,
                now=datetime.now(UTC),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc) or "bad_period") from exc
        if fmt == "xlsx":
            payload = package_xlsx(files)
            media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            filename = f"paquete-{label}.xlsx"
        else:
            payload = package_zip(files)
            media = "application/zip"
            filename = f"paquete-{label}.zip"
        runtime().store.record_report_download(
            tenant_id(),
            report_id="package",
            period_id=label,
            date_from=start,
            date_to=end,
            format=fmt,
            actor_name=actor.name,
            actor_user_id=actor.user_id,
        )
        return Response(
            content=payload,
            media_type=media,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.get("/api/reports/accounting-package")
    def get_accounting_package(
        request: Request,
        period: str | None = None,
        month: str | None = None,
        export_format: str | None = Query(None, alias="format"),
    ) -> Response:
        """Monthly Contabilidad package: one xlsx with Diario…Hechos (supervisor+)."""
        import calendar
        from datetime import UTC, datetime

        actor = require_supervisor(request)
        from factory_os.domain.journal_accounting_package import build_accounting_package_xlsx
        from factory_os.domain.journal_export import (
            DOWNLOAD_REPORT_ACCOUNTING_PACKAGE,
            REPORT_TYPE_PAQUETE,
            export_filename_slug,
        )
        from factory_os.domain.journal_reports import (
            balance_sheet,
            general_ledger,
            income_statement,
            trial_balance,
        )
        from factory_os.domain.reports import excel_available, package_window

        fmt = (export_format or "xlsx").strip().lower()
        if fmt != "xlsx":
            raise HTTPException(status_code=400, detail="bad_format")
        if not excel_available():
            raise HTTPException(status_code=501, detail="excel_unavailable")

        try:
            start, end, label = package_window(
                month=month,
                period=period,
                now=datetime.now(UTC),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc) or "bad_period") from exc

        # Inclusive calendar days for Contabilidad queries (same as on-screen filters).
        raw_month = (month or "").strip()
        if raw_month:
            year_s, mon_s = label.split("-", 1)
            year_i = int(year_s)
            mon_i = int(mon_s)
            last_day = calendar.monthrange(year_i, mon_i)[1]
            from_raw = f"{label}-01"
            to_raw = f"{label}-{last_day:02d}"
            period_preset: str | None = None
        else:
            from_raw = None
            to_raw = None
            period_preset = "month"

        journal_view = _journal_query_view(
            period=period_preset,
            date_from_raw=from_raw,
            date_to_raw=to_raw,
        )
        _shop, _tenant, entries, accounts, period_info = _journal_period_bundle(
            period=period_preset,
            date_from_raw=from_raw,
            date_to_raw=to_raw,
        )
        ledger_view = _ledger_query_view(
            period=period_preset,
            source=None,
            status=None,
            category=None,
            method=None,
            date_from_raw=from_raw,
            date_to_raw=to_raw,
        )

        period_label = f"{period_info['from']} → {period_info['to']}"
        if period_info.get("preset"):
            period_label = f"{period_label} ({period_info['preset']})"
        elif label:
            period_label = f"{period_label} ({label})"

        export_header = _journal_export_header(
            actor,
            period_label,
            report_type=REPORT_TYPE_PAQUETE,
        )
        payload = build_accounting_package_xlsx(
            journal_entries=list(journal_view["entries"]),  # type: ignore[arg-type]
            mayor=general_ledger(entries, accounts),
            trial=trial_balance(entries, accounts),
            income=income_statement(entries, accounts),
            balance=balance_sheet(entries, accounts),
            hechos_entries=list(ledger_view["entries"]),  # type: ignore[arg-type]
            header=export_header,
        )
        filename = export_filename_slug(export_header.business_name, "paquete-contable", "xlsx")
        runtime().store.record_report_download(
            tenant_id(),
            report_id=DOWNLOAD_REPORT_ACCOUNTING_PACKAGE,
            period_id=label,
            date_from=start,
            date_to=end,
            format=fmt,
            actor_name=actor.name,
            actor_user_id=actor.user_id,
        )
        return Response(
            content=payload,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.get("/api/reports/{report_name}")
    def get_report(
        report_name: str,
        request: Request,
        period: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        export_format: str | None = Query(None, alias="format"),
    ) -> Response:
        actor = require_supervisor(request)
        from datetime import UTC, datetime

        from factory_os.domain.reports import (
            REPORT_SHEETS,
            excel_available,
            orders_csv,
            parse_report_instant,
            payments_csv,
            report_window,
            rows_to_xlsx,
            stock_csv,
        )

        kind, suffix = _report_name_parts(report_name)
        writers = {"orders": orders_csv, "payments": payments_csv, "stock": stock_csv}
        writer = writers.get(kind)
        if writer is None:
            raise HTTPException(status_code=404, detail="unknown_report")
        fmt = (export_format or suffix or "csv").strip().lower()
        if fmt == "xlsx" and not excel_available():
            raise HTTPException(status_code=501, detail="excel_unavailable")
        if fmt not in {"csv", "xlsx"}:
            raise HTTPException(status_code=400, detail="bad_format")
        try:
            window = report_window(
                period,
                now=datetime.now(UTC),
                date_from=parse_report_instant(date_from),
                date_to=parse_report_instant(date_to),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc) or "bad_period") from exc
        start, end = window if window is not None else (None, None)
        text = writer(runtime().store, tenant_id(), start=start, end=end)
        runtime().store.record_report_download(
            tenant_id(),
            report_id=kind,
            period_id=(period or "").strip().lower(),
            date_from=start,
            date_to=end,
            format=fmt,
            actor_name=actor.name,
            actor_user_id=actor.user_id,
        )
        if fmt == "xlsx":
            payload = rows_to_xlsx([(REPORT_SHEETS[kind], text)])
            return Response(
                content=payload,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": f'attachment; filename="{kind}.xlsx"'},
            )
        return PlainTextResponse(
            text,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{kind}.csv"'},
        )

    @app.post("/api/reminders/run")
    def post_reminders(body: ReminderRunIn, request: Request) -> dict[str, object]:
        """Leave notices. Sending uses the employee who is allowed to, and never confirms a payment."""
        require_human(request)
        from datetime import UTC, datetime

        from factory_os.contracts.employees import EmployeeRole, identity_for
        from factory_os.domain.reports import run_reminders

        shop_rt = runtime()
        tenant = tenant_id()
        now = datetime.now(UTC)
        if not body.send:
            return run_reminders(
                shop_rt.store,
                identity_for(EmployeeRole.ANALYST, tenant),
                shop_rt.channel,
                shop_rt.tools,
                now=now,
                send=False,
            )
        created: list[dict[str, str]] = []
        sent: list[dict[str, str]] = []
        for role in (EmployeeRole.POSTVENTA, EmployeeRole.COBROS):
            part = run_reminders(
                shop_rt.store,
                identity_for(role, tenant),
                shop_rt.channel,
                shop_rt.tools,
                now=now,
                send=True,
            )
            created.extend(part["created"])
            sent.extend(part["sent"])
        return {"created": created, "sent": sent}

    @app.post("/api/reminders/preview")
    def post_reminder_preview(body: ReminderPreviewIn, request: Request) -> dict[str, object]:
        """Show the notice that would go to this customer. Does not send and does not confirm a payment."""
        require_supervisor(request)
        from datetime import UTC, datetime

        from factory_os.domain.reports import preview_customer_reminder

        try:
            customer_id = UUID(body.customer_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="no_notice") from exc
        try:
            return preview_customer_reminder(
                runtime().store,
                tenant_id(),
                customer_id,
                now=datetime.now(UTC),
                kind=body.kind,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc) or "no_notice") from exc

    @app.post("/api/reminders/send")
    def post_reminder_send(body: ReminderSendIn, request: Request) -> dict[str, object]:
        """Send one customer notice after confirm=true. Never changes a payment."""
        require_supervisor(request)
        if not body.confirm:
            raise HTTPException(status_code=400, detail="confirm_required")
        from datetime import UTC, datetime

        from factory_os.domain.reports import send_customer_reminder

        try:
            customer_id = UUID(body.customer_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="no_notice") from exc
        shop_rt = runtime()
        try:
            return send_customer_reminder(
                shop_rt.store,
                tenant_id(),
                shop_rt.channel,
                shop_rt.tools,
                customer_id=customer_id,
                kind=body.kind,
                confirm=True,
                now=datetime.now(UTC),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc) or "no_notice") from exc

    @app.get("/api/suppliers")
    def get_suppliers(
        request: Request,
        active_only: bool = Query(default=True),
    ) -> dict[str, object]:
        require_human(request)
        from factory_os.domain.suppliers import supplier_public

        rows = runtime().store.list_suppliers(tenant_id(), active_only=active_only)
        return {"suppliers": [supplier_public(item) for item in rows]}

    @app.post("/api/suppliers")
    def post_supplier(body: SupplierIn, request: Request) -> dict[str, object]:
        require_human(request)
        from factory_os.domain.suppliers import supplier_public

        try:
            created = runtime().store.create_supplier(
                tenant_id(),
                body.name,
                contact_name=body.contact_name,
                phone=body.phone,
                whatsapp=body.whatsapp,
                email=body.email,
                notes=body.notes,
                payment_terms=body.payment_terms,
                lead_time_days=body.lead_time_days,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return supplier_public(created)

    @app.patch("/api/suppliers/{supplier_id}")
    def patch_supplier(
        supplier_id: str, body: SupplierPatchIn, request: Request
    ) -> dict[str, object]:
        require_human(request)
        from factory_os.domain.suppliers import supplier_public

        try:
            sid = UUID(supplier_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="supplier_not_found") from exc
        try:
            updated = runtime().store.update_supplier(
                tenant_id(),
                sid,
                name=body.name,
                contact_name=body.contact_name,
                phone=body.phone,
                whatsapp=body.whatsapp,
                email=body.email,
                notes=body.notes,
                payment_terms=body.payment_terms,
                lead_time_days=body.lead_time_days,
                active=body.active,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="supplier_not_found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return supplier_public(updated)

    @app.patch("/api/catalog/variants/{variant_sku}/supplier")
    def patch_variant_supplier(
        variant_sku: str, body: VariantSupplierIn, request: Request
    ) -> dict[str, object]:
        require_human(request)
        supplier_id: UUID | None = None
        if body.supplier_id not in (None, ""):
            try:
                supplier_id = UUID(str(body.supplier_id))
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="bad_supplier") from exc
        try:
            record = runtime().store.set_variant_supplier(
                tenant_id(), variant_sku, supplier_id
            )
        except KeyError as exc:
            missing = exc.args[0] if exc.args else None
            detail = (
                "supplier_not_found"
                if supplier_id is not None and missing == supplier_id
                else "variant_not_found"
            )
            raise HTTPException(status_code=404, detail=detail) from exc
        return {
            "variant_sku": record.variant_sku,
            "supplier_id": str(record.supplier_id) if record.supplier_id else None,
        }

    @app.patch("/api/catalog/variants/{variant_sku}/reorder-threshold")
    def patch_variant_reorder_threshold(
        variant_sku: str, body: ReorderThresholdIn, request: Request
    ) -> dict[str, object]:
        require_human(request)
        try:
            record = runtime().store.set_reorder_threshold(
                tenant_id(), variant_sku, body.threshold
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="variant_not_found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "variant_sku": record.variant_sku,
            "reorder_threshold": record.reorder_threshold,
            "stock": record.stock,
        }

    @app.get("/api/stock/low")
    def get_low_stock(request: Request) -> dict[str, object]:
        """Proveedores: alerta de stock bajo (sin contacto automático)."""
        require_human(request)
        from factory_os.domain.suppliers import list_low_stock, low_stock_public

        shop_rt = runtime()
        low_records = list_low_stock(shop_rt.store)
        low = low_stock_public(low_records, limit=50)
        return {
            "low_stock": low,
            "low_stock_count": len(low_records),
            "contact_supplier": False,
            "note": "El contacto automático a proveedores todavía no está habilitado.",
        }

    @app.get("/api/suppliers/replenishment")
    def get_suppliers_replenishment(request: Request) -> dict[str, object]:
        require_human(request)
        from factory_os.domain.replenishment import build_replenishment

        return build_replenishment(runtime().store, tenant_id())

    @app.post("/api/purchase-orders")
    def post_purchase_order(body: PurchaseOrderIn, request: Request) -> dict[str, object]:
        require_human(request)
        from factory_os.domain.purchase_orders import (
            create_draft_purchase_order,
            purchase_order_public,
        )

        supplier_raw = (body.supplier_id or "").strip()
        if not supplier_raw:
            raise HTTPException(status_code=400, detail="supplier_required")
        try:
            supplier_uuid = UUID(supplier_raw)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="bad_supplier") from exc
        line_payload = [
            {
                "variant_sku": line.variant_sku,
                "quantity": line.quantity,
                "unit_cost": line.unit_cost,
                "currency": line.currency,
            }
            for line in (body.lines or [])
        ]
        try:
            order = create_draft_purchase_order(
                runtime().store,
                tenant_id(),
                supplier_uuid,
                line_payload,
                notes=body.notes or "",
            )
        except KeyError as exc:
            key = exc.args[0] if exc.args else None
            detail = (
                "supplier_not_found"
                if key == supplier_uuid
                else "variant_not_found"
            )
            raise HTTPException(status_code=404, detail=detail) from exc
        except ValueError as exc:
            detail = str(exc) if str(exc) else "bad_purchase_order"
            raise HTTPException(status_code=400, detail=detail) from exc
        except InvalidOperation as exc:
            raise HTTPException(status_code=400, detail="bad_unit_cost") from exc
        return purchase_order_public(order)

    @app.get("/api/purchase-orders")
    def get_purchase_orders(
        request: Request,
        status: str | None = Query(default=None),
    ) -> dict[str, object]:
        require_human(request)
        from factory_os.domain.purchase_orders import (
            list_purchase_orders,
            purchase_order_public,
        )

        rows = list_purchase_orders(runtime().store, tenant_id(), status=status)
        return {
            "purchase_orders": [
                purchase_order_public(item, include_lines=False) for item in rows
            ]
        }

    @app.get("/api/purchase-orders/{order_id}")
    def get_purchase_order_detail(order_id: str, request: Request) -> dict[str, object]:
        require_human(request)
        from factory_os.domain.purchase_orders import (
            get_purchase_order,
            purchase_order_public,
        )

        try:
            oid = UUID(order_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="purchase_order_not_found") from exc
        order = get_purchase_order(runtime().store, tenant_id(), oid)
        if order is None:
            raise HTTPException(status_code=404, detail="purchase_order_not_found")
        return purchase_order_public(order)

    def _purchase_order_http(exc: Exception, *, order_id: UUID | None = None) -> HTTPException:
        if isinstance(exc, KeyError):
            key = exc.args[0] if exc.args else None
            if order_id is not None and key == order_id:
                return HTTPException(status_code=404, detail="purchase_order_not_found")
            if isinstance(key, UUID):
                return HTTPException(status_code=404, detail="not_found")
            return HTTPException(status_code=404, detail="variant_not_found")
        if isinstance(exc, InvalidOperation):
            return HTTPException(status_code=400, detail="bad_unit_cost")
        if isinstance(exc, ValueError):
            detail = str(exc) if str(exc) else "bad_purchase_order"
            return HTTPException(status_code=400, detail=detail)
        return HTTPException(status_code=400, detail="bad_purchase_order")

    @app.patch("/api/purchase-orders/{order_id}")
    def patch_purchase_order(
        order_id: str, body: PurchaseOrderStatusIn, request: Request
    ) -> dict[str, object]:
        require_supervisor(request)
        from factory_os.domain.purchase_orders import (
            purchase_order_public,
            transition_purchase_order,
        )

        try:
            oid = UUID(order_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="purchase_order_not_found") from exc
        try:
            order = transition_purchase_order(
                runtime().store, tenant_id(), oid, body.status
            )
        except (KeyError, ValueError, InvalidOperation) as exc:
            raise _purchase_order_http(exc, order_id=oid) from exc
        return purchase_order_public(order)

    @app.post("/api/purchase-orders/{order_id}/send-whatsapp")
    def post_purchase_order_send_whatsapp(
        order_id: str,
        body: PurchaseOrderSendWhatsappIn,
        request: Request,
    ) -> dict[str, object]:
        """Preview or confirm WhatsApp to supplier. Marks sent only after a successful send."""
        require_supervisor(request)
        from factory_os.domain.purchase_order_whatsapp import (
            confirm_send_purchase_order,
            preview_send_purchase_order,
        )

        try:
            oid = UUID(order_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="purchase_order_not_found") from exc
        store = runtime().store
        tid = tenant_id()
        if not body.confirm:
            try:
                return preview_send_purchase_order(store, tid, oid)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail="purchase_order_not_found") from exc
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc) or "bad_purchase_order") from exc
        shop_rt = runtime()
        settings = cfg
        template = (settings.whatsapp_supplier_order_template or "").strip() or None
        template_lang = (settings.whatsapp_supplier_order_template_lang or "es").strip() or "es"
        try:
            result = confirm_send_purchase_order(
                store,
                tid,
                oid,
                shop_rt.channel,
                template_name=template,
                template_lang=template_lang,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="purchase_order_not_found") from exc
        except ValueError as exc:
            detail = str(exc) or "bad_purchase_order"
            raise HTTPException(status_code=400, detail=detail) from exc
        return result

    @app.post("/api/purchase-orders/{order_id}/receive")
    def post_purchase_order_receive(
        order_id: str, body: PurchaseOrderReceiveIn, request: Request
    ) -> dict[str, object]:
        require_human(request)
        from factory_os.domain.purchase_orders import (
            purchase_order_public,
            receive_purchase_order,
        )

        try:
            oid = UUID(order_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="purchase_order_not_found") from exc
        payload = [
            {
                "variant_sku": line.variant_sku,
                "quantity": line.quantity,
                "unit_cost": line.unit_cost,
                "currency": line.currency,
            }
            for line in (body.lines or [])
        ]
        try:
            order = receive_purchase_order(
                runtime().store,
                tenant_id(),
                oid,
                payload,
                payment_method=(body.payment_method or "cash").strip() or "cash",
            )
        except (KeyError, ValueError, InvalidOperation) as exc:
            raise _purchase_order_http(exc, order_id=oid) from exc
        return purchase_order_public(order)

    @app.post("/api/purchase-orders/{order_id}/payments")
    def post_purchase_order_payment(
        order_id: str, body: PurchaseOrderPaymentIn, request: Request
    ) -> dict[str, object]:
        require_supervisor(request)
        from factory_os.domain.purchase_orders import (
            purchase_order_public,
            register_supplier_payment,
        )

        try:
            oid = UUID(order_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="purchase_order_not_found") from exc
        try:
            amount = Decimal((body.amount or "").strip().replace(",", "."))
            order = register_supplier_payment(
                runtime().store,
                tenant_id(),
                oid,
                amount=amount,
                method=body.method,
                currency=(body.currency or "BOB").strip() or "BOB",
            )
        except (KeyError, ValueError, InvalidOperation) as exc:
            raise _purchase_order_http(exc, order_id=oid) from exc
        return purchase_order_public(order)

    @app.get("/api/purchase-orders/{order_id}/attachments")
    def list_purchase_order_attachments(order_id: str, request: Request) -> dict[str, object]:
        require_human(request)
        try:
            oid = UUID(order_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="purchase_order_not_found") from exc
        shop_rt = runtime()
        tenant = tenant_id()
        if shop_rt.store.get_purchase_order(tenant, oid) is None:
            raise HTTPException(status_code=404, detail="purchase_order_not_found")
        return _entity_attachments_payload(shop_rt.store, tenant, "purchase_order", oid)

    @app.post("/api/purchase-orders/{order_id}/attachments")
    async def post_purchase_order_attachment(order_id: str, request: Request) -> dict[str, object]:
        """Attach image/pdf to a purchase order. No stock or payment side effects."""
        from factory_os.domain.entity_media import EntityMediaError, store_entity_attachment

        actor = require_human(request)
        try:
            oid = UUID(order_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="purchase_order_not_found") from exc
        shop_rt = runtime()
        tenant = tenant_id()
        if shop_rt.store.get_purchase_order(tenant, oid) is None:
            raise HTTPException(status_code=404, detail="purchase_order_not_found")
        upload_name, part_type, data, note = await _read_attachment_upload(request)
        part_mime = (part_type or "").split(";", 1)[0].strip().lower() or None
        try:
            store_entity_attachment(
                shop_rt.store,
                tenant,
                entity_type="purchase_order",
                entity_id=oid,
                data=data,
                mime=part_mime,
                filename=upload_name,
                uploaded_by=actor.name,
                note=note,
            )
        except EntityMediaError as exc:
            code = str(exc) or "bad_type"
            if code == "unknown_entity":
                raise HTTPException(status_code=404, detail="purchase_order_not_found") from exc
            raise HTTPException(status_code=400, detail=code) from exc
        return _entity_attachments_payload(shop_rt.store, tenant, "purchase_order", oid)

    @app.post("/api/stock/receive")
    def post_stock_receive(body: StockReceiveIn, request: Request) -> dict[str, object]:
        require_human(request)
        from datetime import datetime

        sku = body.variant_sku.strip()
        if not sku or body.quantity < 1:
            raise HTTPException(status_code=400, detail="bad_receive")
        cost_raw = (body.unit_cost or "").strip()
        if not cost_raw:
            raise HTTPException(status_code=400, detail="unit_cost_required")
        supplier_raw = (body.supplier_id or "").strip()
        supplier_uuid: UUID | None = None
        if supplier_raw:
            try:
                supplier_uuid = UUID(supplier_raw)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="bad_supplier") from exc
        received_stamp = None
        received_raw = (body.received_at or "").strip()
        if received_raw:
            try:
                received_stamp = datetime.fromisoformat(received_raw.replace("Z", "+00:00"))
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="bad_received_at") from exc
        shop_rt = runtime()
        try:
            cost = Decimal(cost_raw.replace(",", "."))
            if cost <= 0:
                raise HTTPException(status_code=400, detail="bad_purchase")
            receipt = shop_rt.store.receive_purchase(
                tenant_id(),
                sku,
                body.quantity,
                cost,
                (body.currency or "BOB").strip() or "BOB",
                payment_method=(body.payment_method or "cash").strip() or "cash",
                supplier_id=supplier_uuid,
                received_at=received_stamp,
            )
            record = shop_rt.store.get_variant(tenant_id(), sku)
        except KeyError as exc:
            key = str(exc.args[0]) if exc.args else ""
            detail = "supplier_not_found" if supplier_uuid and key == str(supplier_uuid) else "variant_not_found"
            raise HTTPException(status_code=404, detail=detail) from exc
        except ValueError as exc:
            detail = str(exc) if str(exc) in {"bad_purchase", "bad_payment_method"} else "bad_stock"
            raise HTTPException(status_code=400, detail=detail) from exc
        except InvalidOperation as exc:
            raise HTTPException(status_code=400, detail="bad_purchase") from exc
        return {
            "variant_sku": sku,
            "name": record.name if record else sku,
            "received": body.quantity,
            "stock": record.stock if record else 0,
            "purchase_id": str(receipt.id),
            "unit_cost": str(receipt.unit_cost),
            "currency": receipt.currency,
            "payment_method": receipt.payment_method,
            "supplier_id": str(receipt.supplier_id) if receipt.supplier_id else None,
            "received_at": receipt.received_at.isoformat() if receipt.received_at else None,
        }

    def _ledger_query_view(
        *,
        period: str | None,
        source: str | None,
        status: str | None,
        category: str | None,
        method: str | None,
        date_from_raw: str | None,
        date_to_raw: str | None,
    ) -> dict[str, object]:
        """Resolve period, totals, source breakdown, and hydrated filtered rows."""
        from factory_os.domain.ledger import sum_ledger, sync_facts
        from factory_os.domain.ledger_export import breakdown_by_source
        from factory_os.domain.ledger_query import (
            filter_ledger_entries,
            hydrate_ledger_entry,
            period_totals_entries,
            resolve_ledger_period,
        )

        shop_rt = runtime()
        tenant = tenant_id()
        sync_facts(shop_rt.store, tenant)
        entries = shop_rt.store.list_ledger(tenant)

        date_from, date_to, preset = resolve_ledger_period(
            period,
            date_from_raw,
            date_to_raw,
        )
        totals_rows = period_totals_entries(entries, date_from=date_from, date_to=date_to)
        incoming, outgoing, balance = sum_ledger(totals_rows)
        breakdown = breakdown_by_source(totals_rows)

        table_rows = filter_ledger_entries(
            entries,
            date_from=date_from,
            date_to=date_to,
            source=source,
            status=status,
        )
        hydrated = [hydrate_ledger_entry(shop_rt.store, tenant, entry) for entry in table_rows]
        if (category or "").strip() or (method or "").strip():
            hydrated = filter_ledger_entries(
                hydrated,
                category=category,
                method=method,
            )

        return {
            "period": {
                "from": date_from.isoformat(),
                "to": date_to.isoformat(),
                "preset": preset,
            },
            "in": str(incoming),
            "out": str(outgoing),
            "balance": str(balance),
            "breakdown": breakdown,
            "entries": hydrated,
        }

    @app.get("/api/ledger/export")
    def export_ledger(
        request: Request,
        export_format: str | None = Query(None, alias="format"),
        period: str | None = None,
        source: str | None = None,
        status: str | None = None,
        category: str | None = None,
        method: str | None = None,
    ) -> Response:
        """Export filtered ledger entries as CSV, XLSX, or a minimal PDF (supervisor+)."""
        actor = require_supervisor(request)
        from factory_os.domain.journal_export import (
            DOWNLOAD_REPORT_LEDGER_HECHOS,
            REPORT_TYPE_HECHOS,
            export_filename_slug,
        )
        from factory_os.domain.ledger_export import entries_to_csv, entries_to_pdf, hechos_to_xlsx

        kind = (export_format or "").strip().lower()
        if kind not in {"csv", "pdf", "xlsx"}:
            raise HTTPException(status_code=400, detail="bad_format")

        view = _ledger_query_view(
            period=period,
            source=source,
            status=status,
            category=category,
            method=method,
            date_from_raw=request.query_params.get("from"),
            date_to_raw=request.query_params.get("to"),
        )
        hydrated = list(view["entries"])  # type: ignore[arg-type]
        period_info = view["period"]  # type: ignore[assignment]
        period_label = f"{period_info['from']} → {period_info['to']}"
        if period_info.get("preset"):
            period_label = f"{period_label} ({period_info['preset']})"

        if kind == "csv":
            body = entries_to_csv(hydrated)
            _record_contabilidad_download(
                actor,
                report_id=DOWNLOAD_REPORT_LEDGER_HECHOS,
                export_format=kind,
                period=period,
                period_info=period_info,  # type: ignore[arg-type]
            )
            return Response(
                content=body,
                media_type="text/csv; charset=utf-8",
                headers={"Content-Disposition": 'attachment; filename="ledger_export.csv"'},
            )
        if kind == "xlsx":
            export_header = _journal_export_header(
                actor,
                period_label,
                report_type=REPORT_TYPE_HECHOS,
            )
            payload = hechos_to_xlsx(hydrated, header=export_header)
            filename = export_filename_slug(export_header.business_name, "hechos", "xlsx")
            _record_contabilidad_download(
                actor,
                report_id=DOWNLOAD_REPORT_LEDGER_HECHOS,
                export_format=kind,
                period=period,
                period_info=period_info,  # type: ignore[arg-type]
            )
            return Response(
                content=payload,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )
        pdf_bytes = entries_to_pdf(
            hydrated,
            period_label=period_label,
            totals={"in": str(view["in"]), "out": str(view["out"]), "balance": str(view["balance"])},
            breakdown=view["breakdown"],  # type: ignore[arg-type]
        )
        _record_contabilidad_download(
            actor,
            report_id=DOWNLOAD_REPORT_LEDGER_HECHOS,
            export_format=kind,
            period=period,
            period_info=period_info,  # type: ignore[arg-type]
        )
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="ledger_export.pdf"'},
        )

    @app.get("/api/ledger")
    def get_ledger(
        request: Request,
        period: str | None = None,
        source: str | None = None,
        status: str | None = None,
        category: str | None = None,
        method: str | None = None,
    ) -> dict[str, object]:
        require_human(request)
        # Explicit ISO bounds override period presets (FastAPI reserves `from`).
        return _ledger_query_view(
            period=period,
            source=source,
            status=status,
            category=category,
            method=method,
            date_from_raw=request.query_params.get("from"),
            date_to_raw=request.query_params.get("to"),
        )

    def _journal_period_bundle(
        *,
        period: str | None,
        date_from_raw: str | None,
        date_to_raw: str | None,
    ) -> tuple[object, object, list, list, dict[str, object]]:
        """Sync facts/journal seed, resolve period, return entries + accounts + period dict."""
        from factory_os.domain.chart_accounts import ensure_chart_seed
        from factory_os.domain.journal import filter_journal_entries
        from factory_os.domain.ledger import sync_facts
        from factory_os.domain.ledger_query import resolve_ledger_period

        shop_rt = runtime()
        tenant = tenant_id()
        sync_facts(shop_rt.store, tenant)
        ensure_chart_seed(shop_rt.store, tenant)
        date_from, date_to, preset = resolve_ledger_period(
            period,
            date_from_raw,
            date_to_raw,
        )
        entries = filter_journal_entries(
            shop_rt.store.list_journal_entries(tenant),
            date_from=date_from,
            date_to=date_to,
        )
        accounts = shop_rt.store.list_chart_accounts(tenant)
        period_info: dict[str, object] = {
            "from": date_from.isoformat(),
            "to": date_to.isoformat(),
            "preset": preset,
        }
        return shop_rt, tenant, entries, accounts, period_info

    def _journal_query_view(
        *,
        period: str | None,
        date_from_raw: str | None,
        date_to_raw: str | None,
    ) -> dict[str, object]:
        """Sync journal, resolve period, and return hydrated double-entry rows."""
        from factory_os.domain.journal import hydrate_journal_entry

        shop_rt, tenant, entries, _accounts, period_info = _journal_period_bundle(
            period=period,
            date_from_raw=date_from_raw,
            date_to_raw=date_to_raw,
        )
        hydrated = [hydrate_journal_entry(shop_rt.store, tenant, entry) for entry in entries]
        return {
            "period": period_info,
            "entries": hydrated,
        }

    def _serialize_trial_balance(raw: dict[str, object]) -> dict[str, object]:
        return {
            "rows": [
                {
                    "code": row["code"],
                    "name": row["name"],
                    "debit": str(row["debit"]),
                    "credit": str(row["credit"]),
                }
                for row in raw["rows"]  # type: ignore[index]
            ],
            "total_debit": str(raw["total_debit"]),
            "total_credit": str(raw["total_credit"]),
            "balanced": bool(raw["balanced"]),
        }

    def _serialize_general_ledger(raw: dict[str, object]) -> dict[str, object]:
        accounts_out: list[dict[str, object]] = []
        for account in raw.get("accounts") or []:  # type: ignore[union-attr]
            lines_out: list[dict[str, object]] = []
            for line in account.get("lines") or []:
                entry_at = line.get("entry_at")
                lines_out.append(
                    {
                        "entry_at": entry_at.isoformat() if entry_at is not None else None,
                        "entry_id": str(line["entry_id"]),
                        "kind": line["kind"],
                        "memo": line.get("memo") or "",
                        "debit": str(line["debit"]),
                        "credit": str(line["credit"]),
                        "balance": str(line["balance"]),
                    }
                )
            accounts_out.append(
                {
                    "code": account["code"],
                    "name": account["name"],
                    "opening": str(account.get("opening", "0")),
                    "lines": lines_out,
                    "closing_balance": str(account["closing_balance"]),
                }
            )
        return {"accounts": accounts_out}

    def _serialize_income_statement(raw: dict[str, object]) -> dict[str, object]:
        return {
            "revenue": str(raw["revenue"]),
            "cogs": str(raw.get("cogs") or "0"),
            "expenses": str(raw["expenses"]),
            "draws": str(raw["draws"]),
            "result": str(raw["result"]),
            "currency": raw.get("currency") or "BOB",
            "note": raw.get("note") or "",
        }

    def _serialize_balance_sheet(raw: dict[str, object]) -> dict[str, object]:
        rows_out: list[dict[str, object]] = []
        for row in raw.get("rows") or []:  # type: ignore[union-attr]
            rows_out.append(
                {
                    "code": row["code"],
                    "name": row["name"],
                    "account_type": row["account_type"],
                    "balance": str(row["balance"]),
                }
            )
        by_type_raw = raw.get("by_type") or {}
        by_type: dict[str, list[dict[str, object]]] = {}
        if isinstance(by_type_raw, dict):
            for key, items in by_type_raw.items():
                by_type[str(key)] = [
                    {
                        "code": item["code"],
                        "name": item["name"],
                        "account_type": item["account_type"],
                        "balance": str(item["balance"]),
                    }
                    for item in items
                ]
        return {
            "assets": str(raw["assets"]),
            "liabilities": str(raw["liabilities"]),
            "equity": str(raw["equity"]),
            "equity_draws": str(raw["equity_draws"]),
            "net_income": str(raw.get("net_income") or "0"),
            "balanced_check": bool(raw["balanced_check"]),
            "rows": rows_out,
            "by_type": by_type,
        }

    def _journal_export_header(
        actor: PanelActor,
        period_label: str,
        *,
        report_type: str | None = None,
    ):
        """Build Contabilidad export header; period_closed stubbed False until close lookup is cheap."""
        from factory_os.domain.journal_export import (
            JournalExportHeader,
            REPORT_TYPE_DIARIO,
            format_generated_at,
        )
        from factory_os.domain.knowledge import load_shop_pack, sanitize_shop_pack, spoken_shop_name

        shop_rt = runtime()
        stored = shop_rt.store.get_shop_knowledge(tenant_id())
        pack = sanitize_shop_pack(stored if stored is not None else load_shop_pack())
        return JournalExportHeader(
            business_name=spoken_shop_name(pack),
            report_type=report_type or REPORT_TYPE_DIARIO,
            period_label=period_label,
            generated_at=format_generated_at(),
            actor_name=actor.name,
            period_closed=False,
        )

    def _record_contabilidad_download(
        actor: PanelActor,
        *,
        report_id: str,
        export_format: str,
        period: str | None,
        date_from: object | None = None,
        date_to: object | None = None,
        period_info: dict[str, object] | None = None,
    ) -> None:
        """Persist Contabilidad export in report_download_log after bytes are built."""
        from datetime import datetime

        start = date_from
        end = date_to
        if period_info is not None:
            if start is None:
                start = period_info.get("from")
            if end is None:
                end = period_info.get("to")

        def _as_dt(value: object | None) -> datetime | None:
            if value is None:
                return None
            if isinstance(value, datetime):
                return value
            text = str(value).strip()
            if not text:
                return None
            return datetime.fromisoformat(text)

        runtime().store.record_report_download(
            tenant_id(),
            report_id=report_id,
            period_id=(period or "").strip().lower(),
            date_from=_as_dt(start),
            date_to=_as_dt(end),
            format=export_format,
            actor_name=actor.name,
            actor_user_id=actor.user_id,
        )

    @app.get("/api/journal/export")
    def export_journal(
        request: Request,
        export_format: str | None = Query(None, alias="format"),
        period: str | None = None,
    ) -> Response:
        """Export filtered journal entries as CSV, XLSX, or a minimal PDF (supervisor+)."""
        actor = require_supervisor(request)
        from factory_os.domain.journal_export import (
            DOWNLOAD_REPORT_JOURNAL,
            entries_to_csv,
            entries_to_pdf,
            entries_to_xlsx,
            export_filename_slug,
        )

        kind = (export_format or "").strip().lower()
        if kind not in {"csv", "pdf", "xlsx"}:
            raise HTTPException(status_code=400, detail="bad_format")

        view = _journal_query_view(
            period=period,
            date_from_raw=request.query_params.get("from"),
            date_to_raw=request.query_params.get("to"),
        )
        hydrated = list(view["entries"])  # type: ignore[arg-type]
        period_info = view["period"]  # type: ignore[assignment]
        period_label = f"{period_info['from']} → {period_info['to']}"
        if period_info.get("preset"):
            period_label = f"{period_label} ({period_info['preset']})"
        export_header = _journal_export_header(actor, period_label)
        filename = export_filename_slug(export_header.business_name, "diario", kind)

        if kind == "csv":
            body = entries_to_csv(hydrated, header=export_header)
            _record_contabilidad_download(
                actor,
                report_id=DOWNLOAD_REPORT_JOURNAL,
                export_format=kind,
                period=period,
                period_info=period_info,  # type: ignore[arg-type]
            )
            return Response(
                content=body,
                media_type="text/csv; charset=utf-8",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )
        if kind == "xlsx":
            payload = entries_to_xlsx(hydrated, header=export_header)
            _record_contabilidad_download(
                actor,
                report_id=DOWNLOAD_REPORT_JOURNAL,
                export_format=kind,
                period=period,
                period_info=period_info,  # type: ignore[arg-type]
            )
            return Response(
                content=payload,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )
        pdf_bytes = entries_to_pdf(hydrated, period_label=period_label, header=export_header)
        _record_contabilidad_download(
            actor,
            report_id=DOWNLOAD_REPORT_JOURNAL,
            export_format=kind,
            period=period,
            period_info=period_info,  # type: ignore[arg-type]
        )
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.get("/api/journal/trial-balance", response_model=None)
    def get_journal_trial_balance(
        request: Request,
        period: str | None = None,
        export_format: str | None = Query(None, alias="format"),
    ):
        """Trial balance for the managerial journal period; csv/xlsx export is supervisor+."""
        from factory_os.domain.journal_export import (
            DOWNLOAD_REPORT_COMPROBACION,
            REPORT_TYPE_COMPROBACION,
            export_filename_slug,
            trial_balance_to_xlsx,
        )
        from factory_os.domain.journal_reports import trial_balance, trial_balance_to_csv

        kind = (export_format or "").strip().lower()
        actor = None
        if kind in ("csv", "xlsx"):
            actor = require_supervisor(request)
        else:
            require_human(request)
            if kind:
                raise HTTPException(status_code=400, detail="bad_format")

        _shop, _tenant, entries, accounts, period_info = _journal_period_bundle(
            period=period,
            date_from_raw=request.query_params.get("from"),
            date_to_raw=request.query_params.get("to"),
        )
        raw = trial_balance(entries, accounts)
        serialized = _serialize_trial_balance(raw)
        if kind == "csv":
            body = trial_balance_to_csv(serialized)
            assert actor is not None
            _record_contabilidad_download(
                actor,
                report_id=DOWNLOAD_REPORT_COMPROBACION,
                export_format=kind,
                period=period,
                period_info=period_info,
            )
            return Response(
                content=body,
                media_type="text/csv; charset=utf-8",
                headers={
                    "Content-Disposition": 'attachment; filename="trial_balance.csv"',
                },
            )
        if kind == "xlsx":
            period_label = f"{period_info['from']} → {period_info['to']}"
            if period_info.get("preset"):
                period_label = f"{period_label} ({period_info['preset']})"
            export_header = _journal_export_header(
                actor,
                period_label,
                report_type=REPORT_TYPE_COMPROBACION,
            )
            filename = export_filename_slug(export_header.business_name, "comprobacion", "xlsx")
            payload = trial_balance_to_xlsx(raw, header=export_header)
            assert actor is not None
            _record_contabilidad_download(
                actor,
                report_id=DOWNLOAD_REPORT_COMPROBACION,
                export_format=kind,
                period=period,
                period_info=period_info,
            )
            return Response(
                content=payload,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )
        return {"period": period_info, **serialized}

    @app.get("/api/journal/ledger", response_model=None)
    def get_journal_ledger(
        request: Request,
        period: str | None = None,
        account: str | None = None,
        export_format: str | None = Query(None, alias="format"),
    ):
        """General ledger (mayor) with running balances; xlsx export is supervisor+."""
        from factory_os.domain.journal_export import (
            DOWNLOAD_REPORT_MAYOR,
            REPORT_TYPE_MAYOR,
            export_filename_slug,
            ledger_to_xlsx,
        )
        from factory_os.domain.journal_reports import general_ledger

        kind = (export_format or "").strip().lower()
        if kind == "xlsx":
            actor = require_supervisor(request)
        else:
            require_human(request)
            if kind:
                raise HTTPException(status_code=400, detail="bad_format")

        _shop, _tenant, entries, accounts, period_info = _journal_period_bundle(
            period=period,
            date_from_raw=request.query_params.get("from"),
            date_to_raw=request.query_params.get("to"),
        )
        raw = general_ledger(entries, accounts, account_code=account)
        if kind != "xlsx":
            return {"period": period_info, **_serialize_general_ledger(raw)}

        period_label = f"{period_info['from']} → {period_info['to']}"
        if period_info.get("preset"):
            period_label = f"{period_label} ({period_info['preset']})"
        export_header = _journal_export_header(
            actor,
            period_label,
            report_type=REPORT_TYPE_MAYOR,
        )
        filename = export_filename_slug(export_header.business_name, "mayor", "xlsx")
        payload = ledger_to_xlsx(raw, header=export_header)
        _record_contabilidad_download(
            actor,
            report_id=DOWNLOAD_REPORT_MAYOR,
            export_format=kind,
            period=period,
            period_info=period_info,
        )
        return Response(
            content=payload,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.get("/api/journal/income", response_model=None)
    def get_journal_income(
        request: Request,
        period: str | None = None,
        export_format: str | None = Query(None, alias="format"),
    ):
        """Managerial income statement; xlsx/pdf export is supervisor+ (ADR-011 Export)."""
        from factory_os.domain.journal_export import (
            DOWNLOAD_REPORT_RESULTADO,
            REPORT_TYPE_RESULTADO,
            export_filename_slug,
            income_to_pdf,
            income_to_xlsx,
        )
        from factory_os.domain.journal_reports import income_statement

        kind = (export_format or "").strip().lower()
        if kind in {"xlsx", "pdf"}:
            actor = require_supervisor(request)
        else:
            require_human(request)
            if kind:
                raise HTTPException(status_code=400, detail="bad_format")

        _shop, _tenant, entries, accounts, period_info = _journal_period_bundle(
            period=period,
            date_from_raw=request.query_params.get("from"),
            date_to_raw=request.query_params.get("to"),
        )
        raw = income_statement(entries, accounts)
        if not kind:
            return {"period": period_info, **_serialize_income_statement(raw)}

        period_label = f"{period_info['from']} → {period_info['to']}"
        if period_info.get("preset"):
            period_label = f"{period_label} ({period_info['preset']})"
        export_header = _journal_export_header(
            actor,
            period_label,
            report_type=REPORT_TYPE_RESULTADO,
        )
        filename = export_filename_slug(export_header.business_name, "resultado", kind)
        if kind == "xlsx":
            payload = income_to_xlsx(raw, header=export_header)
            _record_contabilidad_download(
                actor,
                report_id=DOWNLOAD_REPORT_RESULTADO,
                export_format=kind,
                period=period,
                period_info=period_info,
            )
            return Response(
                content=payload,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )
        pdf_bytes = income_to_pdf(raw, header=export_header)
        _record_contabilidad_download(
            actor,
            report_id=DOWNLOAD_REPORT_RESULTADO,
            export_format=kind,
            period=period,
            period_info=period_info,
        )
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.get("/api/journal/balance-sheet", response_model=None)
    def get_journal_balance_sheet(
        request: Request,
        period: str | None = None,
        export_format: str | None = Query(None, alias="format"),
    ):
        """Managerial balance sheet; xlsx/pdf export is supervisor+ (ADR-011 Export)."""
        from factory_os.domain.journal_export import (
            DOWNLOAD_REPORT_BALANCE,
            REPORT_TYPE_BALANCE,
            balance_to_pdf,
            balance_to_xlsx,
            export_filename_slug,
        )
        from factory_os.domain.journal_reports import balance_sheet

        kind = (export_format or "").strip().lower()
        if kind in {"xlsx", "pdf"}:
            actor = require_supervisor(request)
        else:
            require_human(request)
            if kind:
                raise HTTPException(status_code=400, detail="bad_format")

        _shop, _tenant, entries, accounts, period_info = _journal_period_bundle(
            period=period,
            date_from_raw=request.query_params.get("from"),
            date_to_raw=request.query_params.get("to"),
        )
        raw = balance_sheet(entries, accounts)
        if not kind:
            return {"period": period_info, **_serialize_balance_sheet(raw)}

        period_label = f"{period_info['from']} → {period_info['to']}"
        if period_info.get("preset"):
            period_label = f"{period_label} ({period_info['preset']})"
        export_header = _journal_export_header(
            actor,
            period_label,
            report_type=REPORT_TYPE_BALANCE,
        )
        filename = export_filename_slug(export_header.business_name, "balance", kind)
        if kind == "xlsx":
            payload = balance_to_xlsx(raw, header=export_header)
            _record_contabilidad_download(
                actor,
                report_id=DOWNLOAD_REPORT_BALANCE,
                export_format=kind,
                period=period,
                period_info=period_info,
            )
            return Response(
                content=payload,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )
        pdf_bytes = balance_to_pdf(raw, header=export_header)
        _record_contabilidad_download(
            actor,
            report_id=DOWNLOAD_REPORT_BALANCE,
            export_format=kind,
            period=period,
            period_info=period_info,
        )
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.get("/api/journal/bank-recon", response_model=None)
    def get_journal_bank_recon(
        request: Request,
        period: str | None = None,
        export_format: str | None = Query(None, alias="format"),
    ):
        """Suggest matches between Banco journal lines and confirmed payments; xlsx is supervisor+."""
        from factory_os.domain.journal_bank_recon import bank_recon_suggest
        from factory_os.domain.journal_export import (
            DOWNLOAD_REPORT_CONCILIACION,
            REPORT_TYPE_CONCILIACION,
            bank_recon_to_xlsx,
            export_filename_slug,
        )
        from factory_os.domain.ledger_query import resolve_ledger_period

        kind = (export_format or "").strip().lower()
        actor = None
        if kind == "xlsx":
            actor = require_supervisor(request)
        else:
            require_human(request)
            if kind:
                raise HTTPException(status_code=400, detail="bad_format")

        shop_rt = runtime()
        tenant = tenant_id()
        date_from, date_to, preset = resolve_ledger_period(
            period,
            request.query_params.get("from"),
            request.query_params.get("to"),
        )
        raw = bank_recon_suggest(shop_rt.store, tenant, date_from, date_to)

        if kind == "xlsx":
            period_label = f"{date_from.isoformat()} → {date_to.isoformat()}"
            if preset:
                period_label = f"{period_label} ({preset})"
            export_header = _journal_export_header(
                actor,
                period_label,
                report_type=REPORT_TYPE_CONCILIACION,
            )
            filename = export_filename_slug(export_header.business_name, "conciliacion", "xlsx")
            payload = bank_recon_to_xlsx(raw, header=export_header)
            assert actor is not None
            _record_contabilidad_download(
                actor,
                report_id=DOWNLOAD_REPORT_CONCILIACION,
                export_format=kind,
                period=period,
                date_from=date_from,
                date_to=date_to,
            )
            return Response(
                content=payload,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )

        def _iso(stamp: object) -> str | None:
            if stamp is None:
                return None
            if hasattr(stamp, "isoformat"):
                return stamp.isoformat()  # type: ignore[no-any-return]
            return str(stamp)

        bank_lines = [
            {
                "entry_id": str(item["entry_id"]),
                "entry_at": _iso(item.get("entry_at")),
                "direction": item["direction"],
                "amount": str(item["amount"]),
                "currency": item.get("currency") or "BOB",
                "memo": item.get("memo") or "",
                "origin_source": item.get("origin_source") or "",
                "origin_id": str(item["origin_id"]),
                "matched": bool(item.get("matched")),
            }
            for item in raw["bank_lines"]
        ]
        payments = [
            {
                "payment_id": str(item["payment_id"]),
                "created_at": _iso(item.get("created_at")),
                "amount": str(item["amount"]),
                "currency": item.get("currency") or "BOB",
                "provider": item.get("provider") or "",
                "matched": bool(item.get("matched")),
            }
            for item in raw["payments"]
        ]
        matches = [
            {
                "entry_id": str(item["entry_id"]),
                "payment_id": str(item["payment_id"]),
                "amount": str(item["amount"]),
                "day": item.get("day"),
            }
            for item in raw["matches"]
        ]
        return {
            "period": {
                "from": date_from.isoformat(),
                "to": date_to.isoformat(),
                "preset": preset,
            },
            "bank_lines": bank_lines,
            "payments": payments,
            "matches": matches,
        }

    @app.post("/api/journal/adjustments")
    def post_journal_adjustment(body: JournalAdjustmentIn, request: Request) -> dict[str, object]:
        """Manual balanced adjustment journal (require_human; origin_source=adjustment)."""
        require_human(request)
        from datetime import UTC, datetime
        from uuid import uuid4

        from factory_os.domain.chart_accounts import ensure_chart_seed
        from factory_os.domain.journal import assert_journal_balanced

        if not body.lines or len(body.lines) < 2:
            raise HTTPException(status_code=400, detail="journal_needs_two_lines")
        lines: list[dict[str, object]] = []
        for item in body.lines:
            code = (item.account_code or "").strip()
            direction = (item.direction or "").strip().lower()
            try:
                amount = Decimal(str(item.amount).replace(",", "."))
            except Exception as exc:
                raise HTTPException(status_code=400, detail="bad_journal_line") from exc
            if not code or direction not in {"debit", "credit"} or amount <= 0:
                raise HTTPException(status_code=400, detail="bad_journal_line")
            lines.append(
                {
                    "account_code": code,
                    "direction": direction,
                    "amount": amount,
                    "currency": "BOB",
                }
            )
        try:
            assert_journal_balanced(lines)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="unbalanced_journal") from exc

        shop_rt = runtime()
        tenant = tenant_id()
        ensure_chart_seed(shop_rt.store, tenant)
        origin_id = uuid4()
        try:
            entry = shop_rt.store.add_journal_entry(
                tenant,
                entry_at=datetime.now(UTC),
                origin_source="adjustment",
                origin_id=origin_id,
                kind="post",
                memo=(body.memo or "").strip() or "ajuste manual",
                lines=lines,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "id": str(entry.id),
            "origin_source": entry.origin_source,
            "origin_id": str(entry.origin_id),
            "kind": entry.kind,
            "memo": entry.memo,
        }

    @app.get("/api/journal")
    def get_journal(request: Request, period: str | None = None) -> dict[str, object]:
        """Managerial journal (ADR-011). Period filters match Contabilidad hechos."""
        require_human(request)
        return _journal_query_view(
            period=period,
            date_from_raw=request.query_params.get("from"),
            date_to_raw=request.query_params.get("to"),
        )

    def _serialize_accounting_period(period: object) -> dict[str, object]:
        return {
            "id": str(getattr(period, "id")),
            "from": getattr(period, "date_from").isoformat(),
            "to": getattr(period, "date_to").isoformat(),
            "status": getattr(period, "status"),
            "closed_at": (
                getattr(period, "closed_at").isoformat()
                if getattr(period, "closed_at", None) is not None
                else None
            ),
            "closed_by_name": getattr(period, "closed_by_name", None),
        }

    def _parse_period_bounds(body: JournalPeriodIn) -> tuple[object, object]:
        from datetime import date as date_cls

        try:
            start = date_cls.fromisoformat(body.date_from.strip()[:10])
            end = date_cls.fromisoformat(body.date_to.strip()[:10])
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="bad_period") from exc
        if start > end:
            raise HTTPException(status_code=400, detail="bad_period_range")
        return start, end

    @app.get("/api/journal/periods")
    def list_journal_periods(request: Request) -> dict[str, object]:
        """List accounting periods (open/closed) for Contabilidad (ADR-011 Fase 2)."""
        require_human(request)
        shop_rt = runtime()
        periods = shop_rt.store.list_accounting_periods(tenant_id())
        return {"periods": [_serialize_accounting_period(item) for item in periods]}

    @app.post("/api/journal/periods/close")
    def close_journal_period(body: JournalPeriodIn, request: Request) -> dict[str, object]:
        """Close a date range so new journal posts (and reverses) are rejected."""
        actor = require_human(request)
        start, end = _parse_period_bounds(body)
        shop_rt = runtime()
        try:
            period = shop_rt.store.close_accounting_period(
                tenant_id(),
                date_from=start,
                date_to=end,
                closed_by_name=actor.name,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _serialize_accounting_period(period)

    @app.post("/api/journal/periods/reopen")
    def reopen_journal_period(body: JournalPeriodIn, request: Request) -> dict[str, object]:
        """Reopen a previously closed accounting period."""
        require_human(request)
        start, end = _parse_period_bounds(body)
        shop_rt = runtime()
        try:
            period = shop_rt.store.reopen_accounting_period(
                tenant_id(), date_from=start, date_to=end
            )
        except ValueError as exc:
            detail = str(exc)
            status = 404 if detail == "period_not_found" else 400
            raise HTTPException(status_code=status, detail=detail) from exc
        return _serialize_accounting_period(period)

    @app.post("/api/invoices")
    def post_invoice(body: InvoiceIn, request: Request) -> dict[str, object]:
        """Issue an invoice document. This does not confirm a payment."""
        require_owner(request)
        from factory_os.domain.invoicing import issue_invoice

        try:
            order_id = UUID(body.order_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="bad_order") from exc
        shop_rt = runtime()
        try:
            document = issue_invoice(shop_rt.store, shop_rt.invoices, tenant_id(), order_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="order") from exc
        return {
            "id": str(document.id),
            "order_id": str(document.order_id or ""),
            "status": document.status,
            "external_ref": document.external_ref,
            "amount": str(document.amount),
            "currency": document.currency,
        }

    @app.get("/api/events")
    async def events(request: Request) -> StreamingResponse:
        require_human(request)
        shop_rt = runtime()
        queue = shop_rt.events.subscribe()

        async def generate():
            try:
                yield "event: ping\ndata: {}\n\n"
                while True:
                    try:
                        payload = await asyncio.wait_for(queue.get(), timeout=20)
                        yield f"data: {json.dumps(payload)}\n\n"
                    except asyncio.TimeoutError:
                        yield "event: ping\ndata: {}\n\n"
            finally:
                shop_rt.events.unsubscribe(queue)

        return StreamingResponse(generate(), media_type="text/event-stream")

    return app


app = create_app()


def run() -> None:
    import os

    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("factory_os.api.main:app", host="0.0.0.0", port=port, reload=False)
