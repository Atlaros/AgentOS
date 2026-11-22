from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterable, Protocol
from uuid import UUID, uuid4

from factory_os.domain.analytics_thresholds import AnalyticsThresholds
from factory_os.domain.models import (
    AccountingPeriod,
    ChartAccount,
    Conversation,
    Customer,
    CustomerNote,
    HumanAuditEvent,
    InvoiceDocument,
    JournalEntry,
    JournalLine,
    LedgerEntry,
    ConversationMedia,
    EntityMedia,
    MediaAsset,
    PanelUser,
    ProductMedia,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseReceipt,
    Reminder,
    ReportDownload,
    CashAttachment,
    CashMovement,
    CashSaleTicket,
    CashSession,
    Delivery,
    Order,
    OrderItem,
    Payment,
    PaymentStatus,
    Supplier,
)


@dataclass
class VariantRecord:
    product_sku: str
    variant_sku: str
    name: str
    description: str
    category: str
    attributes: dict[str, Any]
    price: Decimal
    currency: str
    stock: int
    tokens: set[str]
    supplier_id: UUID | None = None
    reorder_threshold: int = 1


class CommerceStore(Protocol):
    tenant_id: UUID

    def require_tenant(self, tenant_id: UUID) -> None: ...
    def iter_variants(self) -> Iterable[VariantRecord]: ...
    def list_embeddings(self) -> dict[str, list[float]]: ...
    def similar_variants(self, query_vec: list[float], limit: int = 40) -> dict[str, float]: ...
    def put_embedding(self, variant_sku: str, embedding: list[float]) -> None: ...
    def get_variant(self, tenant_id: UUID, variant_sku: str) -> VariantRecord | None: ...
    def get_or_create_customer(self, tenant_id: UUID, wa_number: str) -> Customer: ...
    def get_or_create_conversation(self, tenant_id: UUID, customer: Customer) -> Conversation: ...
    def get_customer(self, tenant_id: UUID, customer_id: UUID) -> Customer | None: ...
    def get_conversation(self, tenant_id: UUID, conversation_id: UUID) -> Conversation | None: ...
    def list_conversations(self, tenant_id: UUID) -> list[Conversation]: ...
    def append_message(self, conv: Conversation, role: str, text: str) -> None: ...
    def save_conversation_state(self, conv: Conversation) -> None: ...
    def get_customer_preferences(self, tenant_id: UUID, customer_id: UUID) -> dict[str, str]: ...
    def put_customer_preferences(
        self, tenant_id: UUID, customer_id: UUID, prefs: dict[str, str]
    ) -> None: ...
    def create_order(
        self,
        tenant_id: UUID,
        customer_id: UUID,
        item: OrderItem | None = None,
        *,
        status: str = "open",
        items: list[OrderItem] | None = None,
        discount_amount: Decimal = Decimal("0"),
        hold_minutes: int = 15,
        origin: str = "agent",
        table_label: str = "",
        fulfill_on: date | None = None,
    ) -> Order: ...
    def replace_order_items(
        self,
        tenant_id: UUID,
        order_id: UUID,
        items: list[OrderItem],
        *,
        discount_amount: Decimal | None = None,
    ) -> Order: ...
    def delete_order(self, tenant_id: UUID, order_id: UUID) -> None: ...
    def held_variant_skus(self, tenant_id: UUID) -> set[str]: ...
    def get_order(self, tenant_id: UUID, order_id: UUID) -> Order | None: ...
    def get_order_by_public_number(self, tenant_id: UUID, public_number: str) -> Order | None: ...
    def mark_order_delivered(
        self, tenant_id: UUID, order_id: UUID, *, delivered_by: str = "owner"
    ) -> Order: ...
    def set_order_status(
        self, tenant_id: UUID, order_id: UUID, status: str, *, delivered_by: str = "owner"
    ) -> Order: ...
    def sold_units_by_sku(self, tenant_id: UUID) -> dict[str, int]: ...
    def create_payment(
        self,
        tenant_id: UUID,
        order_id: UUID | None,
        provider: str,
        provider_ref: str,
        amount: Decimal,
        currency: str,
        qr_payload: str,
        *,
        variant_sku: str = "",
        customer_id: UUID | None = None,
    ) -> Payment: ...
    def delete_payment(self, tenant_id: UUID, payment_id: UUID) -> None: ...
    def payment_status(self, tenant_id: UUID, provider_ref: str) -> Payment | None: ...
    def get_payment(self, tenant_id: UUID, payment_id: UUID) -> Payment | None: ...
    def set_payment_status(
        self,
        tenant_id: UUID,
        payment_id_or_ref: UUID | str,
        status: str,
    ) -> Payment: ...
    def payment_for_order(self, tenant_id: UUID, order_id: UUID) -> Payment | None: ...
    def confirm_from_adapter(self, provider_ref: str) -> None: ...
    def record_webhook_event(
        self,
        tenant_id: UUID,
        *,
        event_id: str,
        provider: str,
        provider_ref: str,
        state: str,
        payload: dict[str, Any] | None = None,
    ) -> bool:
        """Return True if this event_id is new (should be applied). False if duplicate."""
        ...
    def update_customer(
        self, tenant_id: UUID, wa_number: str, name: str | None, address: str | None
    ) -> Customer: ...
    def create_delivery(
        self, tenant_id: UUID, order_id: UUID, address: str, recipient_name: str
    ) -> Delivery: ...
    def delivery_for_order(self, tenant_id: UUID, order_id: UUID) -> Delivery | None: ...
    def update_delivery(
        self, tenant_id: UUID, order_id: UUID, address: str, recipient_name: str
    ) -> Delivery: ...
    def adjust_stock(self, tenant_id: UUID, variant_sku: str, delta: int) -> VariantRecord: ...
    def put_variant(self, tenant_id: UUID, record: VariantRecord) -> VariantRecord: ...
    def set_product_image_paths(
        self, tenant_id: UUID, product_sku: str, image_path: str, thumb_path: str
    ) -> int: ...
    def add_media_asset(self, tenant_id: UUID, asset: MediaAsset) -> MediaAsset: ...
    def get_media_asset(self, tenant_id: UUID, asset_id: UUID) -> MediaAsset | None: ...
    def get_media_asset_by_provider_ref(
        self, tenant_id: UUID, provider_ref: str
    ) -> MediaAsset | None: ...
    def add_product_media(self, tenant_id: UUID, link: ProductMedia) -> ProductMedia: ...
    def list_product_media(
        self, tenant_id: UUID, product_sku: str
    ) -> list[ProductMedia]: ...
    def add_conversation_media(
        self, tenant_id: UUID, link: ConversationMedia
    ) -> ConversationMedia: ...
    def list_conversation_media(
        self, tenant_id: UUID, conversation_id: UUID
    ) -> list[ConversationMedia]: ...
    def get_conversation_media(
        self, tenant_id: UUID, link_id: UUID
    ) -> ConversationMedia | None: ...
    def get_conversation_media_by_provider_ref(
        self, tenant_id: UUID, provider_ref: str
    ) -> ConversationMedia | None: ...
    def update_conversation_media_enrichment(
        self,
        tenant_id: UUID,
        link_id: UUID,
        *,
        transcript_text: str | None = None,
        summary_text: str | None = None,
        enrichment_status: str,
        enrichment_error: str | None = None,
    ) -> ConversationMedia: ...
    def add_entity_media(self, tenant_id: UUID, link: EntityMedia) -> EntityMedia: ...
    def list_entity_media(
        self, tenant_id: UUID, entity_type: str, entity_id: UUID
    ) -> list[EntityMedia]: ...
    def set_category_sort(self, tenant_id: UUID, name: str, sort_order: int) -> None: ...
    def category_sort_map(self, tenant_id: UUID) -> dict[str, int]: ...
    def disable_variant(self, tenant_id: UUID, variant_sku: str) -> VariantRecord: ...
    def set_variant_availability(
        self,
        tenant_id: UUID,
        variant_sku: str,
        *,
        available: bool,
        stock: int | None = None,
    ) -> VariantRecord: ...
    def list_orders(self, tenant_id: UUID) -> list[Order]: ...
    def list_payments(self, tenant_id: UUID) -> list[Payment]: ...
    def get_open_cash_session(self, tenant_id: UUID) -> CashSession | None: ...
    def list_cash_sessions(self, tenant_id: UUID, *, status: str | None = None) -> list[CashSession]: ...
    def open_cash_session(
        self,
        tenant_id: UUID,
        opening_float: Decimal,
        currency: str,
        opened_by_name: str,
        opened_by_id: UUID | None = None,
    ) -> CashSession: ...
    def close_cash_session(
        self,
        tenant_id: UUID,
        *,
        counted_cash: Decimal,
        expected_cash: Decimal,
        difference: Decimal,
        note: str,
        closed_by_name: str,
        closed_by_id: UUID | None = None,
    ) -> CashSession: ...
    def reopen_cash_session(
        self,
        tenant_id: UUID,
        *,
        reopened_by_name: str,
        reopened_by_id: UUID | None = None,
    ) -> CashSession: ...
    def record_cash(
        self,
        tenant_id: UUID,
        direction: str,
        amount: Decimal,
        currency: str,
        reason: str,
        *,
        category: str = "",
        method: str = "cash",
        recorded_by_name: str = "sistema",
        recorded_by_id: UUID | None = None,
        ticket_id: UUID | None = None,
    ) -> CashMovement: ...
    def void_cash(
        self,
        tenant_id: UUID,
        movement_id: UUID,
        reason: str,
        voided_by_name: str,
        voided_by_id: UUID | None = None,
    ) -> CashMovement: ...
    def list_cash(self, tenant_id: UUID, session_id: UUID | None = None) -> list[CashMovement]: ...
    def get_cash_movement(self, tenant_id: UUID, movement_id: UUID) -> CashMovement | None: ...
    def list_cash_attachments(
        self, tenant_id: UUID, movement_id: UUID
    ) -> list[CashAttachment]: ...
    def add_cash_attachment(
        self, tenant_id: UUID, attachment: CashAttachment
    ) -> CashAttachment: ...
    def create_cash_sale_ticket(self, tenant_id: UUID, ticket: CashSaleTicket) -> CashSaleTicket: ...
    def set_cash_sale_movement(
        self, tenant_id: UUID, ticket_id: UUID, movement_id: UUID
    ) -> CashSaleTicket: ...
    def get_cash_sale_ticket(self, tenant_id: UUID, ticket_id: UUID) -> CashSaleTicket | None: ...
    def list_cash_sale_tickets(
        self, tenant_id: UUID, session_id: UUID | None = None
    ) -> list[CashSaleTicket]: ...
    def link_cash_sale_payment(
        self,
        tenant_id: UUID,
        ticket_id: UUID,
        payment_id: UUID,
        provider_ref: str,
    ) -> CashSaleTicket: ...
    def cash_sale_ticket_for_payment(
        self, tenant_id: UUID, payment_id: UUID
    ) -> CashSaleTicket | None: ...
    def set_cash_sale_status(
        self, tenant_id: UUID, ticket_id: UUID, status: str
    ) -> CashSaleTicket: ...
    def add_ledger_entry(
        self,
        tenant_id: UUID,
        source: str,
        source_id: UUID,
        direction: str,
        amount: Decimal,
        currency: str,
        *,
        status: str = "recorded",
    ) -> LedgerEntry: ...
    def set_ledger_entry_status(
        self, tenant_id: UUID, source: str, source_id: UUID, status: str
    ) -> LedgerEntry: ...
    def list_ledger(self, tenant_id: UUID) -> list[LedgerEntry]: ...
    def list_chart_accounts(self, tenant_id: UUID) -> list[ChartAccount]: ...
    def upsert_chart_account(
        self,
        tenant_id: UUID,
        *,
        code: str,
        name: str,
        account_type: str,
        is_system: bool = True,
        active: bool = True,
        account_id: UUID | None = None,
    ) -> ChartAccount: ...
    def ensure_chart_accounts(self, tenant_id: UUID) -> list[ChartAccount]: ...
    def add_journal_entry(
        self,
        tenant_id: UUID,
        *,
        entry_at: Any,
        origin_source: str,
        origin_id: UUID,
        kind: str,
        memo: str,
        lines: list[dict[str, Any]],
        reverses_entry_id: UUID | None = None,
    ) -> JournalEntry: ...
    def list_journal_entries(self, tenant_id: UUID) -> list[JournalEntry]: ...
    def list_journal_lines(self, tenant_id: UUID, entry_id: UUID) -> list[JournalLine]: ...
    def get_journal_by_origin(
        self, tenant_id: UUID, origin_source: str, origin_id: UUID, kind: str
    ) -> JournalEntry | None: ...
    def list_accounting_periods(self, tenant_id: UUID) -> list[AccountingPeriod]: ...
    def get_accounting_period(
        self, tenant_id: UUID, *, date_from: Any, date_to: Any
    ) -> AccountingPeriod | None: ...
    def close_accounting_period(
        self,
        tenant_id: UUID,
        *,
        date_from: Any,
        date_to: Any,
        closed_by_name: str = "",
    ) -> AccountingPeriod: ...
    def reopen_accounting_period(
        self, tenant_id: UUID, *, date_from: Any, date_to: Any
    ) -> AccountingPeriod: ...
    def receive_purchase(
        self,
        tenant_id: UUID,
        variant_sku: str,
        quantity: int,
        unit_cost: Decimal,
        currency: str = "BOB",
        payment_method: str = "cash",
        supplier_id: UUID | None = None,
        received_at: Any = None,
        purchase_order_id: UUID | None = None,
    ) -> PurchaseReceipt: ...
    def list_purchases(self, tenant_id: UUID) -> list[PurchaseReceipt]: ...
    def add_invoice_document(
        self, tenant_id: UUID, order_id: UUID, amount: Decimal, currency: str
    ) -> InvoiceDocument: ...
    def set_invoice_status(
        self, tenant_id: UUID, document_id: UUID, status: str, external_ref: str
    ) -> InvoiceDocument: ...
    def list_invoices(self, tenant_id: UUID) -> list[InvoiceDocument]: ...
    def get_shop_knowledge(self, tenant_id: UUID) -> dict[str, Any] | None: ...
    def put_shop_knowledge(self, tenant_id: UUID, payload: dict[str, Any]) -> dict[str, Any]: ...
    def get_analytics_thresholds(self, tenant_id: UUID) -> AnalyticsThresholds: ...
    def put_analytics_thresholds(
        self, tenant_id: UUID, thresholds: AnalyticsThresholds
    ) -> AnalyticsThresholds: ...
    def analytics_digest_sent(self, tenant_id: UUID, business_date: date) -> bool: ...
    def record_analytics_digest(
        self,
        tenant_id: UUID,
        business_date: date,
        alert_type_count: int,
        sent_at: datetime,
    ) -> None: ...
    def list_customers(self, tenant_id: UUID) -> list[Customer]: ...
    def add_customer_note(self, tenant_id: UUID, customer_id: UUID, body: str) -> CustomerNote: ...
    def list_customer_notes(self, tenant_id: UUID, customer_id: UUID) -> list[CustomerNote]: ...
    def list_reminders(self, tenant_id: UUID) -> list[Reminder]: ...
    def add_reminder(self, tenant_id: UUID, customer_id: UUID, kind: str, body: str) -> Reminder: ...
    def mark_reminder_sent(self, tenant_id: UUID, reminder_id: UUID) -> Reminder: ...
    def record_report_download(
        self,
        tenant_id: UUID,
        *,
        report_id: str,
        period_id: str,
        date_from: datetime | None,
        date_to: datetime | None,
        format: str,
        actor_name: str,
        actor_user_id: UUID | None,
    ) -> ReportDownload: ...
    def list_report_downloads(self, tenant_id: UUID, limit: int = 50) -> list[ReportDownload]: ...
    def add_panel_user(
        self,
        tenant_id: UUID,
        name: str,
        email: str,
        role: str,
        secret_salt: str,
        secret_hash: str,
        *,
        pin_salt: str | None = None,
        pin_hash: str | None = None,
        job_title: str = "",
    ) -> PanelUser: ...
    def list_panel_users(self, tenant_id: UUID) -> list[PanelUser]: ...
    def get_panel_user(self, tenant_id: UUID, user_id: UUID) -> PanelUser | None: ...
    def set_panel_user_secret(
        self,
        tenant_id: UUID,
        user_id: UUID,
        secret_salt: str,
        secret_hash: str,
    ) -> PanelUser: ...
    def add_human_audit(
        self,
        tenant_id: UUID,
        actor_id: UUID | None,
        actor_name: str,
        actor_role: str,
        method: str,
        path: str,
    ) -> HumanAuditEvent: ...
    def list_human_audit(self, tenant_id: UUID) -> list[HumanAuditEvent]: ...
    def list_suppliers(self, tenant_id: UUID, *, active_only: bool = True) -> list[Supplier]: ...
    def get_supplier(self, tenant_id: UUID, supplier_id: UUID) -> Supplier | None: ...
    def create_supplier(
        self,
        tenant_id: UUID,
        name: str,
        *,
        contact_name: str = "",
        phone: str = "",
        whatsapp: str = "",
        email: str = "",
        notes: str = "",
        payment_terms: str = "cash",
        lead_time_days: int = 0,
    ) -> Supplier: ...
    def update_supplier(
        self,
        tenant_id: UUID,
        supplier_id: UUID,
        *,
        name: str | None = None,
        contact_name: str | None = None,
        phone: str | None = None,
        whatsapp: str | None = None,
        email: str | None = None,
        notes: str | None = None,
        payment_terms: str | None = None,
        lead_time_days: int | None = None,
        active: bool | None = None,
    ) -> Supplier: ...
    def deactivate_supplier(self, tenant_id: UUID, supplier_id: UUID) -> Supplier: ...
    def set_variant_supplier(
        self, tenant_id: UUID, variant_sku: str, supplier_id: UUID | None
    ) -> VariantRecord: ...
    def set_reorder_threshold(
        self, tenant_id: UUID, variant_sku: str, threshold: int
    ) -> VariantRecord: ...
    def create_purchase_order(
        self,
        tenant_id: UUID,
        supplier_id: UUID,
        lines: list[dict[str, Any]],
        *,
        status: str = "draft",
        notes: str = "",
    ) -> PurchaseOrder: ...
    def list_purchase_orders(
        self, tenant_id: UUID, *, status: str | None = None
    ) -> list[PurchaseOrder]: ...
    def get_purchase_order(
        self, tenant_id: UUID, order_id: UUID
    ) -> PurchaseOrder | None: ...
    def set_purchase_order_status(
        self, tenant_id: UUID, order_id: UUID, status: str
    ) -> PurchaseOrder: ...
    def set_purchase_order_line_received(
        self,
        tenant_id: UUID,
        order_id: UUID,
        line_id: UUID,
        quantity_received: int,
        unit_cost: Decimal | None = None,
    ) -> PurchaseOrderLine: ...
    def set_purchase_order_payment(
        self,
        tenant_id: UUID,
        order_id: UUID,
        *,
        payment_status: str,
        amount_paid: Decimal,
    ) -> PurchaseOrder: ...


class MemoryCommerceStore:
    """Fast in-process shop for unit tests. Durable twin is PostgresCommerceStore."""

    def __init__(self, tenant_id: UUID) -> None:
        self.tenant_id = tenant_id
        self.variants: dict[str, VariantRecord] = {}
        self.customers: dict[str, Customer] = {}
        self.conversations: dict[UUID, Conversation] = {}
        self.orders: dict[UUID, Order] = {}
        self.payments: dict[UUID, Payment] = {}
        self.payments_by_ref: dict[str, Payment] = {}
        self.deliveries: dict[UUID, Delivery] = {}
        self.cash: dict[UUID, CashMovement] = {}
        self.cash_sessions: dict[UUID, CashSession] = {}
        self.cash_sale_tickets: dict[UUID, CashSaleTicket] = {}
        self.cash_attachments: dict[UUID, CashAttachment] = {}
        self.media_assets: dict[UUID, MediaAsset] = {}
        self.product_media: list[ProductMedia] = []
        self.conversation_media: list[ConversationMedia] = []
        self.entity_media: list[EntityMedia] = []
        self.embeddings: dict[str, list[float]] = {}
        self._confirmed_refs: set[str] = set()
        self.customer_prefs: dict[UUID, dict[str, str]] = {}
        self.webhook_events: set[str] = set()
        self.shop_knowledge: dict[str, Any] | None = None
        self.analytics_thresholds: AnalyticsThresholds | None = None
        self.analytics_digest_log: dict[date, dict[str, Any]] = {}
        self.customer_notes: list[CustomerNote] = []
        self.reminders: list[Reminder] = []
        self.report_downloads: list[ReportDownload] = []
        self.panel_users: list[PanelUser] = []
        self.human_audit: list[HumanAuditEvent] = []
        self.suppliers: list[Supplier] = []
        self.purchase_orders: list[PurchaseOrder] = []
        self.ledger: list[LedgerEntry] = []
        self.purchases: list[PurchaseReceipt] = []
        self.invoices: list[InvoiceDocument] = []
        self.chart_accounts: dict[str, ChartAccount] = {}
        self.journal_entries: dict[UUID, JournalEntry] = {}
        self.journal_lines: list[JournalLine] = []
        self.accounting_periods: dict[tuple[Any, Any], AccountingPeriod] = {}
        self.category_sort: dict[str, int] = {}
        self.modifiers: dict[UUID, Any] = {}

    def require_tenant(self, tenant_id: UUID) -> None:
        if tenant_id != self.tenant_id:
            raise PermissionError("cross-tenant access denied")

    def iter_variants(self) -> Iterable[VariantRecord]:
        return self.variants.values()

    def upsert_variant(self, record: VariantRecord) -> None:
        self.variants[record.variant_sku] = record

    def list_embeddings(self) -> dict[str, list[float]]:
        return dict(self.embeddings)

    def similar_variants(self, query_vec: list[float], limit: int = 40) -> dict[str, float]:
        from factory_os.domain.embeddings import cosine

        scored = sorted(
            ((cosine(query_vec, vec), sku) for sku, vec in self.embeddings.items()),
            reverse=True,
        )
        return {sku: sim for sim, sku in scored[:limit]}

    def put_embedding(self, variant_sku: str, embedding: list[float]) -> None:
        self.embeddings[variant_sku] = list(embedding)

    def get_or_create_customer(self, tenant_id: UUID, wa_number: str) -> Customer:
        self.require_tenant(tenant_id)
        existing = self.customers.get(wa_number)
        if existing:
            return existing
        customer = Customer(id=uuid4(), tenant_id=tenant_id, wa_number=wa_number)
        self.customers[wa_number] = customer
        return customer

    def get_or_create_conversation(self, tenant_id: UUID, customer: Customer) -> Conversation:
        self.require_tenant(tenant_id)
        for conv in self.conversations.values():
            if conv.customer_id == customer.id:
                return conv
        conv = Conversation(id=uuid4(), tenant_id=tenant_id, customer_id=customer.id)
        self.conversations[conv.id] = conv
        return conv

    def get_customer(self, tenant_id: UUID, customer_id: UUID) -> Customer | None:
        self.require_tenant(tenant_id)
        for customer in self.customers.values():
            if customer.id == customer_id:
                return customer
        return None

    def list_customers(self, tenant_id: UUID) -> list[Customer]:
        self.require_tenant(tenant_id)
        return list(self.customers.values())

    def add_customer_note(self, tenant_id: UUID, customer_id: UUID, body: str) -> CustomerNote:
        from datetime import UTC, datetime

        self.require_tenant(tenant_id)
        if self.get_customer(tenant_id, customer_id) is None:
            raise KeyError(customer_id)
        text = body.strip()
        if not text:
            raise ValueError("empty_note")
        note = CustomerNote(
            id=uuid4(),
            tenant_id=tenant_id,
            customer_id=customer_id,
            body=text,
            created_at=datetime.now(UTC),
        )
        self.customer_notes.append(note)
        return note

    def list_customer_notes(self, tenant_id: UUID, customer_id: UUID) -> list[CustomerNote]:
        self.require_tenant(tenant_id)
        return [note for note in self.customer_notes if note.customer_id == customer_id]

    def list_reminders(self, tenant_id: UUID) -> list[Reminder]:
        self.require_tenant(tenant_id)
        return list(self.reminders)

    def add_reminder(self, tenant_id: UUID, customer_id: UUID, kind: str, body: str) -> Reminder:
        from datetime import UTC, datetime

        self.require_tenant(tenant_id)
        if kind not in {"follow_up", "repurchase", "collections"}:
            raise ValueError("bad_reminder_kind")
        text = body.strip()
        if not text:
            raise ValueError("empty_reminder")
        if self.get_customer(tenant_id, customer_id) is None:
            raise KeyError(customer_id)
        for current in self.reminders:
            if current.customer_id == customer_id and current.kind == kind and current.sent_at is None:
                return current
        reminder = Reminder(
            id=uuid4(),
            tenant_id=tenant_id,
            customer_id=customer_id,
            kind=kind,
            body=text,
            created_at=datetime.now(UTC),
        )
        self.reminders.append(reminder)
        return reminder

    def mark_reminder_sent(self, tenant_id: UUID, reminder_id: UUID) -> Reminder:
        from datetime import UTC, datetime

        self.require_tenant(tenant_id)
        for reminder in self.reminders:
            if reminder.id == reminder_id:
                reminder.sent_at = datetime.now(UTC)
                return reminder
        raise KeyError(reminder_id)

    def record_report_download(
        self,
        tenant_id: UUID,
        *,
        report_id: str,
        period_id: str,
        date_from: datetime | None,
        date_to: datetime | None,
        format: str,
        actor_name: str,
        actor_user_id: UUID | None,
    ) -> ReportDownload:
        from datetime import UTC, datetime

        self.require_tenant(tenant_id)
        report = report_id.strip()
        fmt = format.strip().lower()
        name = actor_name.strip()
        if not report or not fmt or not name:
            raise ValueError("bad_download")
        row = ReportDownload(
            id=uuid4(),
            tenant_id=tenant_id,
            report_id=report,
            period_id=(period_id or "").strip(),
            date_from=date_from,
            date_to=date_to,
            format=fmt,
            actor_name=name,
            actor_user_id=actor_user_id,
            created_at=datetime.now(UTC),
        )
        self.report_downloads.append(row)
        return row

    def list_report_downloads(self, tenant_id: UUID, limit: int = 50) -> list[ReportDownload]:
        self.require_tenant(tenant_id)
        size = limit if limit > 0 else 50
        return list(reversed(self.report_downloads))[:size]

    def add_panel_user(
        self,
        tenant_id: UUID,
        name: str,
        email: str,
        role: str,
        secret_salt: str,
        secret_hash: str,
        *,
        pin_salt: str | None = None,
        pin_hash: str | None = None,
        job_title: str = "",
    ) -> PanelUser:
        from datetime import UTC, datetime

        from factory_os.domain.panel_access import STORED_PANEL_ROLES

        self.require_tenant(tenant_id)
        cleaned_name = name.strip()
        cleaned_email = email.strip().lower()
        if not cleaned_name:
            raise ValueError("empty_name")
        if "@" not in cleaned_email or cleaned_email.startswith("@") or " " in cleaned_email:
            raise ValueError("bad_email")
        if role not in STORED_PANEL_ROLES:
            raise ValueError("bad_role")
        if any(user.email == cleaned_email for user in self.panel_users):
            raise ValueError("duplicate_email")
        user = PanelUser(
            id=uuid4(),
            tenant_id=tenant_id,
            name=cleaned_name,
            email=cleaned_email,
            role=role,
            secret_salt=secret_salt,
            secret_hash=secret_hash,
            created_at=datetime.now(UTC),
            pin_salt=pin_salt,
            pin_hash=pin_hash,
            job_title=(job_title or "").strip(),
        )
        self.panel_users.append(user)
        return user

    def list_panel_users(self, tenant_id: UUID) -> list[PanelUser]:
        self.require_tenant(tenant_id)
        return list(self.panel_users)

    def get_panel_user(self, tenant_id: UUID, user_id: UUID) -> PanelUser | None:
        self.require_tenant(tenant_id)
        for user in self.panel_users:
            if user.id == user_id:
                return user
        return None

    def set_panel_user_secret(
        self,
        tenant_id: UUID,
        user_id: UUID,
        secret_salt: str,
        secret_hash: str,
    ) -> PanelUser:
        self.require_tenant(tenant_id)
        for index, user in enumerate(self.panel_users):
            if user.id != user_id:
                continue
            if not user.active:
                raise KeyError(user_id)
            updated = PanelUser(
                id=user.id,
                tenant_id=user.tenant_id,
                name=user.name,
                email=user.email,
                role=user.role,
                secret_salt=secret_salt,
                secret_hash=secret_hash,
                active=user.active,
                created_at=user.created_at,
                pin_salt=user.pin_salt,
                pin_hash=user.pin_hash,
                job_title=user.job_title,
            )
            self.panel_users[index] = updated
            return updated
        raise KeyError(user_id)

    def add_human_audit(
        self,
        tenant_id: UUID,
        actor_id: UUID | None,
        actor_name: str,
        actor_role: str,
        method: str,
        path: str,
    ) -> HumanAuditEvent:
        from datetime import UTC, datetime

        from factory_os.domain.panel_access import AUDIT_ROLES

        self.require_tenant(tenant_id)
        if actor_role not in AUDIT_ROLES:
            raise ValueError("bad_role")
        event = HumanAuditEvent(
            id=uuid4(),
            tenant_id=tenant_id,
            actor_id=actor_id,
            actor_name=actor_name.strip(),
            actor_role=actor_role,
            method=method,
            path=path,
            created_at=datetime.now(UTC),
        )
        self.human_audit.append(event)
        return event

    def list_human_audit(self, tenant_id: UUID) -> list[HumanAuditEvent]:
        self.require_tenant(tenant_id)
        return list(self.human_audit)

    def list_suppliers(self, tenant_id: UUID, *, active_only: bool = True) -> list[Supplier]:
        self.require_tenant(tenant_id)
        rows = list(self.suppliers)
        if active_only:
            rows = [item for item in rows if item.active]
        return rows

    def get_supplier(self, tenant_id: UUID, supplier_id: UUID) -> Supplier | None:
        self.require_tenant(tenant_id)
        for item in self.suppliers:
            if item.id == supplier_id:
                return item
        return None

    def create_supplier(
        self,
        tenant_id: UUID,
        name: str,
        *,
        contact_name: str = "",
        phone: str = "",
        whatsapp: str = "",
        email: str = "",
        notes: str = "",
        payment_terms: str = "cash",
        lead_time_days: int = 0,
    ) -> Supplier:
        from datetime import UTC, datetime

        self.require_tenant(tenant_id)
        cleaned = name.strip()
        if not cleaned:
            raise ValueError("bad_name")
        if lead_time_days < 0:
            raise ValueError("bad_lead_time")
        now = datetime.now(UTC)
        supplier = Supplier(
            id=uuid4(),
            tenant_id=tenant_id,
            name=cleaned,
            contact_name=contact_name.strip(),
            phone=phone.strip(),
            whatsapp=whatsapp.strip(),
            email=email.strip(),
            notes=notes.strip(),
            payment_terms=(payment_terms or "cash").strip() or "cash",
            lead_time_days=int(lead_time_days),
            active=True,
            created_at=now,
            updated_at=now,
        )
        self.suppliers.append(supplier)
        return supplier

    def update_supplier(
        self,
        tenant_id: UUID,
        supplier_id: UUID,
        *,
        name: str | None = None,
        contact_name: str | None = None,
        phone: str | None = None,
        whatsapp: str | None = None,
        email: str | None = None,
        notes: str | None = None,
        payment_terms: str | None = None,
        lead_time_days: int | None = None,
        active: bool | None = None,
    ) -> Supplier:
        from datetime import UTC, datetime

        self.require_tenant(tenant_id)
        supplier = self.get_supplier(tenant_id, supplier_id)
        if supplier is None:
            raise KeyError(supplier_id)
        if name is not None:
            cleaned = name.strip()
            if not cleaned:
                raise ValueError("bad_name")
            supplier.name = cleaned
        if contact_name is not None:
            supplier.contact_name = contact_name.strip()
        if phone is not None:
            supplier.phone = phone.strip()
        if whatsapp is not None:
            supplier.whatsapp = whatsapp.strip()
        if email is not None:
            supplier.email = email.strip()
        if notes is not None:
            supplier.notes = notes.strip()
        if payment_terms is not None:
            supplier.payment_terms = payment_terms.strip() or "cash"
        if lead_time_days is not None:
            if lead_time_days < 0:
                raise ValueError("bad_lead_time")
            supplier.lead_time_days = int(lead_time_days)
        if active is not None:
            supplier.active = bool(active)
        supplier.updated_at = datetime.now(UTC)
        return supplier

    def deactivate_supplier(self, tenant_id: UUID, supplier_id: UUID) -> Supplier:
        return self.update_supplier(tenant_id, supplier_id, active=False)

    def set_variant_supplier(
        self, tenant_id: UUID, variant_sku: str, supplier_id: UUID | None
    ) -> VariantRecord:
        self.require_tenant(tenant_id)
        record = self.variants.get(variant_sku)
        if record is None:
            raise KeyError(variant_sku)
        if supplier_id is not None:
            supplier = self.get_supplier(tenant_id, supplier_id)
            if supplier is None:
                raise KeyError(supplier_id)
        record.supplier_id = supplier_id
        return record

    def set_reorder_threshold(
        self, tenant_id: UUID, variant_sku: str, threshold: int
    ) -> VariantRecord:
        self.require_tenant(tenant_id)
        if threshold < 0:
            raise ValueError("bad_threshold")
        record = self.variants.get(variant_sku)
        if record is None:
            raise KeyError(variant_sku)
        record.reorder_threshold = int(threshold)
        return record

    def create_purchase_order(
        self,
        tenant_id: UUID,
        supplier_id: UUID,
        lines: list[dict[str, Any]],
        *,
        status: str = "draft",
        notes: str = "",
    ) -> PurchaseOrder:
        from datetime import UTC, datetime

        self.require_tenant(tenant_id)
        if status not in {"draft", "sent", "partially_received", "received", "cancelled"}:
            raise ValueError("bad_status")
        if not lines:
            raise ValueError("empty_lines")
        if self.get_supplier(tenant_id, supplier_id) is None:
            raise KeyError(supplier_id)
        now = datetime.now(UTC)
        order_id = uuid4()
        po_lines: list[PurchaseOrderLine] = []
        for raw in lines:
            sku = str(raw.get("variant_sku") or "").strip()
            qty = int(raw.get("quantity") or raw.get("quantity_ordered") or 0)
            if not sku or qty < 1:
                raise ValueError("bad_line")
            if sku not in self.variants:
                raise KeyError(sku)
            unit_cost = raw.get("unit_cost")
            cost = None if unit_cost is None else Decimal(str(unit_cost))
            po_lines.append(
                PurchaseOrderLine(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    purchase_order_id=order_id,
                    variant_sku=sku,
                    quantity_ordered=qty,
                    quantity_received=0,
                    unit_cost=cost,
                    currency=str(raw.get("currency") or "BOB") or "BOB",
                )
            )
        order = PurchaseOrder(
            id=order_id,
            tenant_id=tenant_id,
            supplier_id=supplier_id,
            status=status,
            notes=(notes or "").strip(),
            created_at=now,
            updated_at=now,
            lines=po_lines,
        )
        self.purchase_orders.append(order)
        return order

    def list_purchase_orders(
        self, tenant_id: UUID, *, status: str | None = None
    ) -> list[PurchaseOrder]:
        from datetime import UTC, datetime

        self.require_tenant(tenant_id)
        rows = list(self.purchase_orders)
        if status is not None:
            rows = [item for item in rows if item.status == status]
        epoch = datetime.min.replace(tzinfo=UTC)
        return sorted(
            rows,
            key=lambda item: item.created_at or epoch,
            reverse=True,
        )

    def get_purchase_order(
        self, tenant_id: UUID, order_id: UUID
    ) -> PurchaseOrder | None:
        self.require_tenant(tenant_id)
        for item in self.purchase_orders:
            if item.id == order_id:
                return item
        return None

    def set_purchase_order_status(
        self, tenant_id: UUID, order_id: UUID, status: str
    ) -> PurchaseOrder:
        from datetime import UTC, datetime

        self.require_tenant(tenant_id)
        if status not in {"draft", "sent", "partially_received", "received", "cancelled"}:
            raise ValueError("bad_status")
        order = self.get_purchase_order(tenant_id, order_id)
        if order is None:
            raise KeyError(order_id)
        order.status = status
        order.updated_at = datetime.now(UTC)
        return order

    def set_purchase_order_line_received(
        self,
        tenant_id: UUID,
        order_id: UUID,
        line_id: UUID,
        quantity_received: int,
        unit_cost: Decimal | None = None,
    ) -> PurchaseOrderLine:
        from datetime import UTC, datetime

        self.require_tenant(tenant_id)
        if quantity_received < 0:
            raise ValueError("bad_quantity")
        order = self.get_purchase_order(tenant_id, order_id)
        if order is None:
            raise KeyError(order_id)
        for line in order.lines:
            if line.id != line_id:
                continue
            if quantity_received > line.quantity_ordered:
                raise ValueError("over_receive")
            line.quantity_received = int(quantity_received)
            if unit_cost is not None:
                line.unit_cost = Decimal(str(unit_cost))
            order.updated_at = datetime.now(UTC)
            return line
        raise KeyError(line_id)

    def set_purchase_order_payment(
        self,
        tenant_id: UUID,
        order_id: UUID,
        *,
        payment_status: str,
        amount_paid: Decimal,
    ) -> PurchaseOrder:
        from datetime import UTC, datetime

        self.require_tenant(tenant_id)
        status = (payment_status or "").strip().lower()
        if status not in {"unpaid", "partial", "paid"}:
            raise ValueError("bad_payment_status")
        paid = Decimal(str(amount_paid))
        if paid < 0:
            raise ValueError("bad_amount")
        order = self.get_purchase_order(tenant_id, order_id)
        if order is None:
            raise KeyError(order_id)
        order.payment_status = status
        order.amount_paid = paid
        order.updated_at = datetime.now(UTC)
        return order

    def get_conversation(self, tenant_id: UUID, conversation_id: UUID) -> Conversation | None:
        self.require_tenant(tenant_id)
        return self.conversations.get(conversation_id)

    def list_conversations(self, tenant_id: UUID) -> list[Conversation]:
        self.require_tenant(tenant_id)
        return list(reversed(list(self.conversations.values())))

    def append_message(self, conv: Conversation, role: str, text: str) -> None:
        from datetime import UTC, datetime

        conv.messages.append((role, text))
        conv.last_message_at = datetime.now(UTC)
        if conv.id in self.conversations:
            self.conversations.pop(conv.id)
            self.conversations[conv.id] = conv

    def save_conversation_state(self, conv: Conversation) -> None:
        from factory_os.domain.memory import maybe_refresh_summary, prefs_from_working_state

        maybe_refresh_summary(conv)
        prefs = prefs_from_working_state(conv.state)
        if prefs:
            self.put_customer_preferences(conv.tenant_id, conv.customer_id, prefs)
        return None

    def get_customer_preferences(self, tenant_id: UUID, customer_id: UUID) -> dict[str, str]:
        self.require_tenant(tenant_id)
        return dict(self.customer_prefs.get(customer_id) or {})

    def put_customer_preferences(
        self, tenant_id: UUID, customer_id: UUID, prefs: dict[str, str]
    ) -> None:
        self.require_tenant(tenant_id)
        current = dict(self.customer_prefs.get(customer_id) or {})
        for key, value in prefs.items():
            if value:
                current[str(key)] = str(value)
        self.customer_prefs[customer_id] = current

    def get_variant(self, tenant_id: UUID, variant_sku: str) -> VariantRecord | None:
        self.require_tenant(tenant_id)
        return self.variants.get(variant_sku)

    def create_order(
        self,
        tenant_id: UUID,
        customer_id: UUID,
        item: OrderItem | None = None,
        *,
        status: str = "open",
        items: list[OrderItem] | None = None,
        discount_amount: Decimal = Decimal("0"),
        hold_minutes: int = 15,
        origin: str = "agent",
        table_label: str = "",
        fulfill_on: date | None = None,
    ) -> Order:
        self.require_tenant(tenant_id)
        from factory_os.domain.learning import new_public_order_number
        from factory_os.domain.models import ORDER_STATUSES

        from datetime import UTC, datetime

        lines = list(items) if items else ([item] if item is not None else [])
        if not lines:
            raise ValueError("empty_order")
        if status not in ORDER_STATUSES:
            raise ValueError("bad_status")
        origin_clean = (origin or "agent").strip() or "agent"
        if origin_clean not in {"agent", "counter"}:
            raise ValueError("bad_origin")
        order = Order(
            id=uuid4(),
            tenant_id=tenant_id,
            customer_id=customer_id,
            items=lines,
            status=status,
            public_number=new_public_order_number(),
            created_at=datetime.now(UTC),
            discount_amount=discount_amount,
            hold_minutes=hold_minutes,
            origin=origin_clean,
            table_label=(table_label or "").strip(),
            fulfill_on=fulfill_on,
        )
        self.orders[order.id] = order
        return order

    def replace_order_items(
        self,
        tenant_id: UUID,
        order_id: UUID,
        items: list[OrderItem],
        *,
        discount_amount: Decimal | None = None,
    ) -> Order:
        self.require_tenant(tenant_id)
        order = self.orders.get(order_id)
        if order is None:
            raise KeyError("order")
        if not items:
            raise ValueError("empty_order")
        order.items = list(items)
        if discount_amount is not None:
            order.discount_amount = discount_amount
        return order

    def delete_order(self, tenant_id: UUID, order_id: UUID) -> None:
        self.require_tenant(tenant_id)
        self.orders.pop(order_id, None)
        drop_payments = [pid for pid, payment in self.payments.items() if payment.order_id == order_id]
        for pid in drop_payments:
            payment = self.payments.pop(pid)
            self.payments_by_ref.pop(payment.provider_ref, None)
        drop_deliveries = [did for did, delivery in self.deliveries.items() if delivery.order_id == order_id]
        for did in drop_deliveries:
            self.deliveries.pop(did, None)

    def held_variant_skus(self, tenant_id: UUID) -> set[str]:
        self.require_tenant(tenant_id)
        skus: set[str] = set()
        for order in self.orders.values():
            if getattr(order, "origin", "agent") == "counter":
                continue
            if getattr(order, "fulfill_on", None) is not None:
                continue
            if order.status not in {"reserved", "open"}:
                continue
            if order.status == "open":
                payment = next(
                    (item for item in self.payments.values() if item.order_id == order.id),
                    None,
                )
                if payment is not None and payment.status is PaymentStatus.CONFIRMED:
                    continue
            for item in order.items:
                skus.add(item.variant_sku)
        for payment in self.payments.values():
            if (
                payment.order_id is None
                and payment.status is PaymentStatus.PENDING
                and payment.variant_sku
            ):
                skus.add(payment.variant_sku)
        for ticket in self.cash_sale_tickets.values():
            if ticket.status != "pending_qr":
                continue
            for line in ticket.lines:
                skus.add(line.variant_sku)
        return skus

    def get_order(self, tenant_id: UUID, order_id: UUID) -> Order | None:
        self.require_tenant(tenant_id)
        return self.orders.get(order_id)

    def get_order_by_public_number(self, tenant_id: UUID, public_number: str) -> Order | None:
        self.require_tenant(tenant_id)
        needle = (public_number or "").strip().upper()
        for order in self.orders.values():
            if (order.public_number or "").upper() == needle:
                return order
        return None

    def mark_order_delivered(
        self, tenant_id: UUID, order_id: UUID, *, delivered_by: str = "owner"
    ) -> Order:
        self.require_tenant(tenant_id)
        order = self.orders.get(order_id)
        if order is None:
            raise KeyError("order")
        from datetime import UTC, datetime

        order.delivered_at = datetime.now(UTC)
        order.delivered_by = delivered_by
        order.status = "delivered"
        return order

    def set_order_status(
        self, tenant_id: UUID, order_id: UUID, status: str, *, delivered_by: str = "owner"
    ) -> Order:
        self.require_tenant(tenant_id)
        if status not in {"reserved", "placed", "open", "cancelled", "delivered"}:
            raise ValueError("bad_status")
        order = self.orders.get(order_id)
        if order is None:
            raise KeyError("order")
        from datetime import UTC, datetime

        order.status = status
        if status == "delivered":
            order.delivered_at = order.delivered_at or datetime.now(UTC)
            order.delivered_by = order.delivered_by or delivered_by
        else:
            order.delivered_at = None
            order.delivered_by = None
        return order

    def mark_order_stock_applied(self, tenant_id: UUID, order_id: UUID) -> None:
        self.require_tenant(tenant_id)
        order = self.orders.get(order_id)
        if order is None:
            raise KeyError("order")
        order.stock_applied = True

    def sold_units_by_sku(self, tenant_id: UUID) -> dict[str, int]:
        self.require_tenant(tenant_id)
        counts: dict[str, int] = {}
        for order in self.orders.values():
            if order.status == "cancelled":
                continue
            payment = next((item for item in self.payments.values() if item.order_id == order.id), None)
            if payment is None or payment.status is not PaymentStatus.CONFIRMED:
                continue
            for item in order.items:
                counts[item.variant_sku] = counts.get(item.variant_sku, 0) + item.quantity
        return counts

    def create_payment(
        self,
        tenant_id: UUID,
        order_id: UUID | None,
        provider: str,
        provider_ref: str,
        amount: Decimal,
        currency: str,
        qr_payload: str,
        *,
        variant_sku: str = "",
        customer_id: UUID | None = None,
    ) -> Payment:
        self.require_tenant(tenant_id)
        from datetime import UTC, datetime

        payment = Payment(
            id=uuid4(),
            tenant_id=tenant_id,
            order_id=order_id,
            provider=provider,
            provider_ref=provider_ref,
            amount=amount,
            currency=currency,
            status=PaymentStatus.PENDING,
            qr_payload=qr_payload,
            variant_sku=variant_sku,
            customer_id=customer_id,
            created_at=datetime.now(UTC),
        )
        self.payments[payment.id] = payment
        self.payments_by_ref[provider_ref] = payment
        return payment

    def delete_payment(self, tenant_id: UUID, payment_id: UUID) -> None:
        self.require_tenant(tenant_id)
        payment = self.payments.pop(payment_id, None)
        if payment is not None:
            self.payments_by_ref.pop(payment.provider_ref, None)

    def payment_status(self, tenant_id: UUID, provider_ref: str) -> Payment | None:
        self.require_tenant(tenant_id)
        payment = self.payments_by_ref.get(provider_ref)
        if payment is None:
            return None
        if provider_ref in self._confirmed_refs:
            payment.status = PaymentStatus.CONFIRMED
        return payment

    def get_payment(self, tenant_id: UUID, payment_id: UUID) -> Payment | None:
        self.require_tenant(tenant_id)
        return self.payments.get(payment_id)

    def set_payment_status(
        self,
        tenant_id: UUID,
        payment_id_or_ref: UUID | str,
        status: str,
    ) -> Payment:
        self.require_tenant(tenant_id)
        next_status = PaymentStatus(str(status).strip().lower())
        payment: Payment | None = None
        if isinstance(payment_id_or_ref, UUID):
            payment = self.payments.get(payment_id_or_ref)
        else:
            raw = str(payment_id_or_ref).strip()
            try:
                payment = self.payments.get(UUID(raw))
            except ValueError:
                payment = None
            if payment is None:
                payment = self.payments_by_ref.get(raw)
        if payment is None or payment.tenant_id != tenant_id:
            raise ValueError("payment_not_found")
        payment.status = next_status
        return payment

    def payment_for_order(self, tenant_id: UUID, order_id: UUID) -> Payment | None:
        self.require_tenant(tenant_id)
        for payment in self.payments.values():
            if payment.order_id == order_id:
                return payment
        return None

    def confirm_from_adapter(self, provider_ref: str) -> None:
        """Confirm one provider reference. Customer text never reaches this.

        Baneco (or its test double) confirms its own ref. The owner cash helper
        confirms a payment it just created with provider ``cash``. Walk-in QR
        tickets complete without an Order or drawer movement; chat payments
        place the order and mark garments sold.
        """
        from factory_os.domain.cash_sales import complete_walkin_qr_if_pending
        from factory_os.domain.ledger import remember_payment

        self._confirmed_refs.add(provider_ref)
        payment = self.payments_by_ref.get(provider_ref)
        if payment is None:
            return
        payment.status = PaymentStatus.CONFIRMED
        if complete_walkin_qr_if_pending(self, payment):
            remember_payment(self, payment)
            return
        sell_now = False
        if payment.order_id is None and payment.variant_sku and payment.customer_id:
            record = self.variants.get(payment.variant_sku)
            if record is not None:
                order = self.create_order(
                    payment.tenant_id,
                    payment.customer_id,
                    OrderItem(
                        variant_sku=record.variant_sku,
                        name=record.name,
                        quantity=1,
                        unit_price=record.price,
                        currency=record.currency,
                    ),
                    status="placed",
                )
                payment.order_id = order.id
                sell_now = True
        if payment.order_id is not None:
            order = self.orders.get(payment.order_id)
            if order is not None and order.status in {"reserved", "open"}:
                self.set_order_status(payment.tenant_id, order.id, "placed")
                sell_now = True
            if sell_now:
                self._mark_paid_order_sold(payment.tenant_id, payment.order_id)
        remember_payment(self, payment)

    def _mark_paid_order_sold(self, tenant_id: UUID, order_id: UUID) -> None:
        order = self.orders.get(order_id)
        if order is None:
            return
        if order.fulfill_on is not None:
            from factory_os.domain.future_orders import apply_due_future_orders

            apply_due_future_orders(self, tenant_id)
            return
        from factory_os.domain.stock import consume_stock

        for item in order.items:
            if item.variant_sku not in self.variants:
                continue
            consume_stock(self, tenant_id, item.variant_sku, item.quantity)

    def record_webhook_event(
        self,
        tenant_id: UUID,
        *,
        event_id: str,
        provider: str,
        provider_ref: str,
        state: str,
        payload: dict[str, Any] | None = None,
    ) -> bool:
        self.require_tenant(tenant_id)
        if event_id in self.webhook_events:
            return False
        self.webhook_events.add(event_id)
        _ = provider, provider_ref, state, payload
        return True

    def update_customer(self, tenant_id: UUID, wa_number: str, name: str | None, address: str | None) -> Customer:
        self.require_tenant(tenant_id)
        customer = self.get_or_create_customer(tenant_id, wa_number)
        if name:
            customer.name = name
        if address:
            customer.address = address
        return customer

    def create_delivery(self, tenant_id: UUID, order_id: UUID, address: str, recipient_name: str) -> Delivery:
        self.require_tenant(tenant_id)
        delivery = Delivery(
            id=uuid4(),
            tenant_id=tenant_id,
            order_id=order_id,
            address=address,
            recipient_name=recipient_name,
        )
        self.deliveries[delivery.id] = delivery
        return delivery

    def update_delivery(
        self, tenant_id: UUID, order_id: UUID, address: str, recipient_name: str
    ) -> Delivery:
        self.require_tenant(tenant_id)
        delivery = self.delivery_for_order(tenant_id, order_id)
        if delivery is None:
            raise KeyError("delivery")
        delivery.address = address
        delivery.recipient_name = recipient_name
        return delivery

    def delivery_for_order(self, tenant_id: UUID, order_id: UUID) -> Delivery | None:
        self.require_tenant(tenant_id)
        found = [item for item in self.deliveries.values() if item.order_id == order_id]
        return found[-1] if found else None

    def adjust_stock(self, tenant_id: UUID, variant_sku: str, delta: int) -> VariantRecord:
        self.require_tenant(tenant_id)
        record = self.variants[variant_sku]
        new_stock = record.stock + delta
        if new_stock < 0:
            raise ValueError("negative_stock")
        record.stock = new_stock
        return record

    def put_variant(self, tenant_id: UUID, record: VariantRecord) -> VariantRecord:
        self.require_tenant(tenant_id)
        self.upsert_variant(record)
        from factory_os.domain.embeddings import embed_blob, embed_document

        self.put_embedding(record.variant_sku, embed_document(embed_blob(record)))
        return record

    def set_product_image_paths(
        self, tenant_id: UUID, product_sku: str, image_path: str, thumb_path: str
    ) -> int:
        self.require_tenant(tenant_id)
        count = 0
        for record in self.variants.values():
            if record.product_sku != product_sku:
                continue
            record.attributes = dict(record.attributes)
            record.attributes["image_path"] = image_path
            record.attributes["thumb_path"] = thumb_path
            count += 1
        if count == 0:
            raise ValueError("unknown_product")
        return count

    def add_media_asset(self, tenant_id: UUID, asset: MediaAsset) -> MediaAsset:
        self.require_tenant(tenant_id)
        if asset.tenant_id != tenant_id:
            raise PermissionError("cross-tenant access denied")
        ref = (asset.provider_ref or "").strip()
        if ref:
            prior = self.get_media_asset_by_provider_ref(tenant_id, ref)
            if prior is not None:
                return prior
        self.media_assets[asset.id] = asset
        return asset

    def get_media_asset(self, tenant_id: UUID, asset_id: UUID) -> MediaAsset | None:
        self.require_tenant(tenant_id)
        asset = self.media_assets.get(asset_id)
        if asset is None or asset.tenant_id != tenant_id:
            return None
        return asset

    def get_media_asset_by_provider_ref(
        self, tenant_id: UUID, provider_ref: str
    ) -> MediaAsset | None:
        self.require_tenant(tenant_id)
        ref = (provider_ref or "").strip()
        if not ref:
            return None
        for asset in self.media_assets.values():
            if asset.tenant_id == tenant_id and (asset.provider_ref or "").strip() == ref:
                return asset
        return None

    def add_conversation_media(
        self, tenant_id: UUID, link: ConversationMedia
    ) -> ConversationMedia:
        self.require_tenant(tenant_id)
        if link.tenant_id != tenant_id:
            raise PermissionError("cross-tenant access denied")
        ref = (link.provider_ref or "").strip()
        if ref:
            prior = self.get_conversation_media_by_provider_ref(tenant_id, ref)
            if prior is not None:
                return prior
        self.conversation_media.append(link)
        return link

    def list_conversation_media(
        self, tenant_id: UUID, conversation_id: UUID
    ) -> list[ConversationMedia]:
        self.require_tenant(tenant_id)
        rows = [
            item
            for item in self.conversation_media
            if item.tenant_id == tenant_id and item.conversation_id == conversation_id
        ]
        return sorted(rows, key=lambda item: (item.created_at or item.id, item.id))

    def get_conversation_media(
        self, tenant_id: UUID, link_id: UUID
    ) -> ConversationMedia | None:
        self.require_tenant(tenant_id)
        for item in self.conversation_media:
            if item.tenant_id == tenant_id and item.id == link_id:
                return item
        return None

    def get_conversation_media_by_provider_ref(
        self, tenant_id: UUID, provider_ref: str
    ) -> ConversationMedia | None:
        self.require_tenant(tenant_id)
        ref = (provider_ref or "").strip()
        if not ref:
            return None
        for item in self.conversation_media:
            if item.tenant_id == tenant_id and (item.provider_ref or "").strip() == ref:
                return item
        return None

    def update_conversation_media_enrichment(
        self,
        tenant_id: UUID,
        link_id: UUID,
        *,
        transcript_text: str | None = None,
        summary_text: str | None = None,
        enrichment_status: str,
        enrichment_error: str | None = None,
    ) -> ConversationMedia:
        self.require_tenant(tenant_id)
        status = (enrichment_status or "none").strip().lower()
        if status not in {"none", "pending", "ready", "failed"}:
            raise ValueError("bad_enrichment_status")
        for index, item in enumerate(self.conversation_media):
            if item.tenant_id == tenant_id and item.id == link_id:
                updated = ConversationMedia(
                    id=item.id,
                    tenant_id=item.tenant_id,
                    conversation_id=item.conversation_id,
                    asset_id=item.asset_id,
                    direction=item.direction,
                    status=item.status,
                    kind=item.kind,
                    provider_ref=item.provider_ref,
                    message_index=item.message_index,
                    mime=item.mime,
                    filename=item.filename,
                    size_bytes=item.size_bytes,
                    error=item.error,
                    uploaded_by=item.uploaded_by,
                    created_at=item.created_at,
                    transcript_text=transcript_text,
                    summary_text=summary_text,
                    enrichment_status=status,
                    enrichment_error=enrichment_error,
                )
                self.conversation_media[index] = updated
                return updated
        raise KeyError("conversation_media")

    def add_entity_media(self, tenant_id: UUID, link: EntityMedia) -> EntityMedia:
        self.require_tenant(tenant_id)
        if link.tenant_id != tenant_id:
            raise PermissionError("cross-tenant access denied")
        if self.get_media_asset(tenant_id, link.asset_id) is None:
            raise ValueError("unknown_media")
        self.entity_media.append(link)
        return link

    def list_entity_media(
        self, tenant_id: UUID, entity_type: str, entity_id: UUID
    ) -> list[EntityMedia]:
        self.require_tenant(tenant_id)
        etype = (entity_type or "").strip().lower()
        rows = [
            item
            for item in self.entity_media
            if item.tenant_id == tenant_id
            and item.entity_type == etype
            and item.entity_id == entity_id
        ]
        return sorted(rows, key=lambda item: (item.created_at or item.id, item.id))

    def add_product_media(self, tenant_id: UUID, link: ProductMedia) -> ProductMedia:
        self.require_tenant(tenant_id)
        if link.tenant_id != tenant_id:
            raise PermissionError("cross-tenant access denied")
        if self.get_media_asset(tenant_id, link.asset_id) is None:
            raise ValueError("unknown_media")
        has_product = any(
            record.product_sku == link.product_sku for record in self.variants.values()
        )
        if not has_product:
            raise ValueError("unknown_product")
        existing = [
            item
            for item in self.product_media
            if item.tenant_id == tenant_id and item.product_sku == link.product_sku
        ]
        if link.is_primary:
            for item in existing:
                item.is_primary = False
        elif not existing:
            link.is_primary = True
        self.product_media.append(link)
        return link

    def list_product_media(
        self, tenant_id: UUID, product_sku: str
    ) -> list[ProductMedia]:
        self.require_tenant(tenant_id)
        rows = [
            item
            for item in self.product_media
            if item.tenant_id == tenant_id and item.product_sku == product_sku
        ]
        return sorted(rows, key=lambda item: (item.sort_order, item.created_at or item.id))

    def set_category_sort(self, tenant_id: UUID, name: str, sort_order: int) -> None:
        self.require_tenant(tenant_id)
        self.category_sort[name] = int(sort_order)

    def category_sort_map(self, tenant_id: UUID) -> dict[str, int]:
        self.require_tenant(tenant_id)
        return dict(self.category_sort)

    def create_modifier(
        self,
        tenant_id: UUID,
        *,
        name: str,
        price_delta: Decimal,
        currency: str = "BOB",
    ):
        from factory_os.domain.modifiers import CatalogModifier

        self.require_tenant(tenant_id)
        row = CatalogModifier(
            id=uuid4(),
            tenant_id=tenant_id,
            name=name,
            price_delta=price_delta,
            currency=currency or "BOB",
        )
        self.modifiers[row.id] = row
        return row

    def list_modifiers(self, tenant_id: UUID) -> list:
        self.require_tenant(tenant_id)
        rows = [row for row in self.modifiers.values() if row.tenant_id == tenant_id]
        return sorted(rows, key=lambda row: (row.name.casefold(), str(row.id)))

    def get_modifier(self, tenant_id: UUID, modifier_id: UUID):
        self.require_tenant(tenant_id)
        row = self.modifiers.get(modifier_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return row

    def disable_variant(self, tenant_id: UUID, variant_sku: str) -> VariantRecord:
        self.require_tenant(tenant_id)
        return self.set_variant_availability(tenant_id, variant_sku, available=False)

    def set_variant_availability(
        self,
        tenant_id: UUID,
        variant_sku: str,
        *,
        available: bool,
        stock: int | None = None,
    ) -> VariantRecord:
        self.require_tenant(tenant_id)
        record = self.variants[variant_sku]
        record.attributes = dict(record.attributes)
        if available:
            record.attributes.pop("disabled", None)
            if stock is not None:
                if stock < 0:
                    raise ValueError("bad_stock")
                record.stock = stock
            elif record.stock < 1:
                record.stock = 1
        else:
            record.attributes["disabled"] = True
            record.stock = 0 if stock is None else max(0, stock)
        return record

    def list_orders(self, tenant_id: UUID) -> list[Order]:
        self.require_tenant(tenant_id)
        return list(self.orders.values())

    def list_payments(self, tenant_id: UUID) -> list[Payment]:
        self.require_tenant(tenant_id)
        return list(self.payments.values())

    def get_open_cash_session(self, tenant_id: UUID) -> CashSession | None:
        self.require_tenant(tenant_id)
        for session in self.cash_sessions.values():
            if session.tenant_id == tenant_id and session.status == "open":
                return session
        return None

    def list_cash_sessions(self, tenant_id: UUID, *, status: str | None = None) -> list[CashSession]:
        self.require_tenant(tenant_id)
        rows = [
            session
            for session in self.cash_sessions.values()
            if session.tenant_id == tenant_id and (status is None or session.status == status)
        ]
        return sorted(
            rows,
            key=lambda item: item.closed_at or item.opened_at or item.id.hex,
            reverse=True,
        )

    def open_cash_session(
        self,
        tenant_id: UUID,
        opening_float: Decimal,
        currency: str,
        opened_by_name: str,
        opened_by_id: UUID | None = None,
    ) -> CashSession:
        from datetime import UTC, datetime

        self.require_tenant(tenant_id)
        if self.get_open_cash_session(tenant_id) is not None:
            raise ValueError("session_open")
        if opening_float < 0:
            raise ValueError("bad_amount")
        session = CashSession(
            id=uuid4(),
            tenant_id=tenant_id,
            status="open",
            opening_float=opening_float,
            currency=currency or "BOB",
            opened_by_name=opened_by_name,
            opened_by_id=opened_by_id,
            opened_at=datetime.now(UTC),
        )
        self.cash_sessions[session.id] = session
        return session

    def close_cash_session(
        self,
        tenant_id: UUID,
        *,
        counted_cash: Decimal,
        expected_cash: Decimal,
        difference: Decimal,
        note: str,
        closed_by_name: str,
        closed_by_id: UUID | None = None,
    ) -> CashSession:
        from datetime import UTC, datetime

        self.require_tenant(tenant_id)
        session = self.get_open_cash_session(tenant_id)
        if session is None:
            raise ValueError("session_required")
        session.status = "closed"
        session.counted_cash = counted_cash
        session.expected_cash = expected_cash
        session.difference = difference
        session.close_note = note
        session.closed_by_name = closed_by_name
        session.closed_by_id = closed_by_id
        session.closed_at = datetime.now(UTC)
        return session

    def reopen_cash_session(
        self,
        tenant_id: UUID,
        *,
        reopened_by_name: str,
        reopened_by_id: UUID | None = None,
    ) -> CashSession:
        self.require_tenant(tenant_id)
        if self.get_open_cash_session(tenant_id) is not None:
            raise ValueError("session_open")
        closed = self.list_cash_sessions(tenant_id, status="closed")
        if not closed:
            raise ValueError("session_required")
        session = closed[0]
        session.status = "open"
        session.closed_at = None
        session.closed_by_name = None
        session.closed_by_id = None
        session.counted_cash = None
        session.expected_cash = None
        session.difference = None
        session.close_note = None
        _ = reopened_by_name, reopened_by_id
        return session

    def record_cash(
        self,
        tenant_id: UUID,
        direction: str,
        amount: Decimal,
        currency: str,
        reason: str,
        *,
        category: str = "",
        method: str = "cash",
        recorded_by_name: str = "sistema",
        recorded_by_id: UUID | None = None,
        ticket_id: UUID | None = None,
    ) -> CashMovement:
        from datetime import UTC, datetime

        self.require_tenant(tenant_id)
        if direction not in {"in", "out"}:
            raise ValueError("bad_direction")
        if amount <= 0:
            raise ValueError("bad_amount")
        session = self.get_open_cash_session(tenant_id)
        if session is None:
            raise ValueError("session_required")
        movement = CashMovement(
            id=uuid4(),
            tenant_id=tenant_id,
            direction=direction,
            amount=amount,
            currency=currency or "BOB",
            reason=reason,
            session_id=session.id,
            created_at=datetime.now(UTC),
            category=category or "",
            method=(method or "cash").strip() or "cash",
            status="recorded",
            recorded_by_name=(recorded_by_name or "sistema").strip() or "sistema",
            recorded_by_id=recorded_by_id,
            ticket_id=ticket_id,
        )
        self.cash[movement.id] = movement
        from factory_os.domain.ledger import remember_cash

        remember_cash(self, movement)
        return movement

    def create_cash_sale_ticket(self, tenant_id: UUID, ticket: CashSaleTicket) -> CashSaleTicket:
        self.require_tenant(tenant_id)
        if ticket.tenant_id != tenant_id:
            raise PermissionError("cross-tenant access denied")
        self.cash_sale_tickets[ticket.id] = ticket
        return ticket

    def set_cash_sale_movement(
        self, tenant_id: UUID, ticket_id: UUID, movement_id: UUID
    ) -> CashSaleTicket:
        self.require_tenant(tenant_id)
        ticket = self.cash_sale_tickets.get(ticket_id)
        if ticket is None or ticket.tenant_id != tenant_id:
            raise ValueError("ticket_not_found")
        ticket.movement_id = movement_id
        return ticket

    def link_cash_sale_payment(
        self,
        tenant_id: UUID,
        ticket_id: UUID,
        payment_id: UUID,
        provider_ref: str,
    ) -> CashSaleTicket:
        self.require_tenant(tenant_id)
        ticket = self.cash_sale_tickets.get(ticket_id)
        if ticket is None or ticket.tenant_id != tenant_id:
            raise ValueError("ticket_not_found")
        ticket.payment_id = payment_id
        ticket.provider_ref = (provider_ref or "").strip() or None
        return ticket

    def cash_sale_ticket_for_payment(
        self, tenant_id: UUID, payment_id: UUID
    ) -> CashSaleTicket | None:
        self.require_tenant(tenant_id)
        for ticket in self.cash_sale_tickets.values():
            if ticket.tenant_id == tenant_id and ticket.payment_id == payment_id:
                return ticket
        return None

    def set_cash_sale_status(
        self, tenant_id: UUID, ticket_id: UUID, status: str
    ) -> CashSaleTicket:
        self.require_tenant(tenant_id)
        ticket = self.cash_sale_tickets.get(ticket_id)
        if ticket is None or ticket.tenant_id != tenant_id:
            raise ValueError("ticket_not_found")
        ticket.status = status
        return ticket

    def get_cash_sale_ticket(self, tenant_id: UUID, ticket_id: UUID) -> CashSaleTicket | None:
        self.require_tenant(tenant_id)
        ticket = self.cash_sale_tickets.get(ticket_id)
        if ticket is None or ticket.tenant_id != tenant_id:
            return None
        return ticket

    def list_cash_sale_tickets(
        self, tenant_id: UUID, session_id: UUID | None = None
    ) -> list[CashSaleTicket]:
        self.require_tenant(tenant_id)
        rows = [
            ticket
            for ticket in self.cash_sale_tickets.values()
            if ticket.tenant_id == tenant_id
            and (session_id is None or ticket.session_id == session_id)
        ]
        return sorted(
            rows,
            key=lambda item: item.created_at or item.id.hex,
            reverse=True,
        )

    def void_cash(
        self,
        tenant_id: UUID,
        movement_id: UUID,
        reason: str,
        voided_by_name: str,
        voided_by_id: UUID | None = None,
    ) -> CashMovement:
        from datetime import UTC, datetime

        from factory_os.domain.ledger import void_cash_ledger

        self.require_tenant(tenant_id)
        reason_clean = (reason or "").strip()
        if not reason_clean:
            raise ValueError("void_reason_required")
        movement = self.cash.get(movement_id)
        if movement is None or movement.tenant_id != tenant_id:
            raise ValueError("movement_not_found")
        if movement.status == "voided":
            raise ValueError("already_voided")
        movement.status = "voided"
        movement.void_reason = reason_clean
        movement.voided_by_name = (voided_by_name or "").strip() or "sistema"
        movement.voided_by_id = voided_by_id
        movement.voided_at = datetime.now(UTC)
        void_cash_ledger(self, movement)
        return movement

    def list_cash(self, tenant_id: UUID, session_id: UUID | None = None) -> list[CashMovement]:
        self.require_tenant(tenant_id)
        rows = list(self.cash.values())
        if session_id is not None:
            rows = [item for item in rows if item.session_id == session_id]
        return rows

    def get_cash_movement(self, tenant_id: UUID, movement_id: UUID) -> CashMovement | None:
        self.require_tenant(tenant_id)
        movement = self.cash.get(movement_id)
        if movement is None or movement.tenant_id != tenant_id:
            return None
        return movement

    def list_cash_attachments(
        self, tenant_id: UUID, movement_id: UUID
    ) -> list[CashAttachment]:
        self.require_tenant(tenant_id)
        rows = [
            item
            for item in self.cash_attachments.values()
            if item.tenant_id == tenant_id and item.movement_id == movement_id
        ]
        return sorted(
            rows,
            key=lambda item: item.created_at or item.id,
            reverse=True,
        )

    def add_cash_attachment(
        self, tenant_id: UUID, attachment: CashAttachment
    ) -> CashAttachment:
        self.require_tenant(tenant_id)
        if attachment.tenant_id != tenant_id:
            raise PermissionError("cross-tenant access denied")
        movement = self.get_cash_movement(tenant_id, attachment.movement_id)
        if movement is None:
            raise ValueError("movement_not_found")
        self.cash_attachments[attachment.id] = attachment
        return attachment

    def add_ledger_entry(
        self,
        tenant_id: UUID,
        source: str,
        source_id: UUID,
        direction: str,
        amount: Decimal,
        currency: str,
        *,
        status: str = "recorded",
    ) -> LedgerEntry:
        from datetime import UTC, datetime

        self.require_tenant(tenant_id)
        if source not in {"payment", "cash", "purchase"} or direction not in {"in", "out"}:
            raise ValueError("bad_ledger")
        if amount <= 0:
            raise ValueError("bad_amount")
        status_clean = (status or "recorded").strip() or "recorded"
        if status_clean not in {"recorded", "voided"}:
            raise ValueError("bad_ledger_status")
        for current in self.ledger:
            if current.source == source and current.source_id == source_id:
                return current
        entry = LedgerEntry(
            id=uuid4(),
            tenant_id=tenant_id,
            source=source,
            source_id=source_id,
            direction=direction,
            amount=amount,
            currency=currency or "BOB",
            created_at=datetime.now(UTC),
            status=status_clean,
        )
        self.ledger.append(entry)
        return entry

    def set_ledger_entry_status(
        self, tenant_id: UUID, source: str, source_id: UUID, status: str
    ) -> LedgerEntry:
        self.require_tenant(tenant_id)
        status_clean = (status or "").strip()
        if status_clean not in {"recorded", "voided"}:
            raise ValueError("bad_ledger_status")
        for current in self.ledger:
            if current.source == source and current.source_id == source_id:
                current.status = status_clean
                return current
        raise ValueError("ledger_entry_not_found")

    def list_ledger(self, tenant_id: UUID) -> list[LedgerEntry]:
        self.require_tenant(tenant_id)
        return list(self.ledger)

    def list_chart_accounts(self, tenant_id: UUID) -> list[ChartAccount]:
        self.require_tenant(tenant_id)
        return sorted(self.chart_accounts.values(), key=lambda account: account.code)

    def upsert_chart_account(
        self,
        tenant_id: UUID,
        *,
        code: str,
        name: str,
        account_type: str,
        is_system: bool = True,
        active: bool = True,
        account_id: UUID | None = None,
    ) -> ChartAccount:
        from datetime import UTC, datetime

        from factory_os.domain.chart_accounts import ACCOUNT_TYPES

        self.require_tenant(tenant_id)
        code_clean = (code or "").strip()
        name_clean = (name or "").strip()
        type_clean = (account_type or "").strip()
        if not code_clean or not name_clean or type_clean not in ACCOUNT_TYPES:
            raise ValueError("bad_chart_account")
        existing = self.chart_accounts.get(code_clean)
        if existing is not None:
            existing.name = name_clean
            existing.account_type = type_clean
            existing.is_system = bool(is_system)
            existing.active = bool(active)
            return existing
        account = ChartAccount(
            id=account_id or uuid4(),
            tenant_id=tenant_id,
            code=code_clean,
            name=name_clean,
            account_type=type_clean,
            is_system=bool(is_system),
            active=bool(active),
            created_at=datetime.now(UTC),
        )
        self.chart_accounts[code_clean] = account
        return account

    def ensure_chart_accounts(self, tenant_id: UUID) -> list[ChartAccount]:
        from factory_os.domain.chart_accounts import SEED_ACCOUNTS

        self.require_tenant(tenant_id)
        for seed in SEED_ACCOUNTS:
            if seed["code"] not in self.chart_accounts:
                self.upsert_chart_account(
                    tenant_id,
                    code=seed["code"],
                    name=seed["name"],
                    account_type=seed["account_type"],
                    is_system=True,
                    active=True,
                )
        return self.list_chart_accounts(tenant_id)

    def _resolve_journal_account(
        self, tenant_id: UUID, line: dict[str, Any]
    ) -> ChartAccount:
        account_id = line.get("account_id")
        account_code = (line.get("account_code") or "").strip()
        if account_id is not None:
            for account in self.chart_accounts.values():
                if account.id == account_id:
                    return account
            raise ValueError("account_not_found")
        if account_code:
            account = self.chart_accounts.get(account_code)
            if account is None:
                raise ValueError("account_not_found")
            return account
        raise ValueError("account_required")

    def add_journal_entry(
        self,
        tenant_id: UUID,
        *,
        entry_at: Any,
        origin_source: str,
        origin_id: UUID,
        kind: str,
        memo: str,
        lines: list[dict[str, Any]],
        reverses_entry_id: UUID | None = None,
    ) -> JournalEntry:
        from datetime import UTC, datetime

        from factory_os.domain.accounting_periods import assert_period_open_for_entry
        from factory_os.domain.journal import (
            JOURNAL_KINDS,
            LINE_DIRECTIONS,
            ORIGIN_SOURCES,
            assert_journal_balanced,
        )

        self.require_tenant(tenant_id)
        source = (origin_source or "").strip()
        kind_clean = (kind or "").strip()
        if source not in ORIGIN_SOURCES or kind_clean not in JOURNAL_KINDS:
            raise ValueError("bad_journal")
        existing = self.get_journal_by_origin(tenant_id, source, origin_id, kind_clean)
        if existing is not None:
            return existing
        if not lines:
            raise ValueError("journal_needs_two_lines")
        for line in lines:
            direction = str(line.get("direction") or "").strip()
            amount = Decimal(str(line.get("amount")))
            if direction not in LINE_DIRECTIONS or amount <= 0:
                raise ValueError("bad_journal_line")
        assert_journal_balanced(lines)
        entry_id = uuid4()
        when = entry_at or datetime.now(UTC)
        assert_period_open_for_entry(self, tenant_id, when)
        built_lines: list[JournalLine] = []
        for line in lines:
            account = self._resolve_journal_account(tenant_id, line)
            built = JournalLine(
                id=uuid4(),
                tenant_id=tenant_id,
                entry_id=entry_id,
                account_id=account.id,
                direction=str(line["direction"]).strip(),
                amount=Decimal(str(line["amount"])),
                currency=(str(line.get("currency") or "BOB").strip() or "BOB"),
                account_code=account.code,
            )
            built_lines.append(built)
            self.journal_lines.append(built)
        entry = JournalEntry(
            id=entry_id,
            tenant_id=tenant_id,
            entry_at=when,
            origin_source=source,
            origin_id=origin_id,
            kind=kind_clean,
            memo=(memo or "").strip(),
            reverses_entry_id=reverses_entry_id,
            lines=built_lines,
            created_at=datetime.now(UTC),
        )
        self.journal_entries[entry_id] = entry
        return entry

    def list_journal_lines(self, tenant_id: UUID, entry_id: UUID) -> list[JournalLine]:
        self.require_tenant(tenant_id)
        return [line for line in self.journal_lines if line.entry_id == entry_id]

    def list_journal_entries(self, tenant_id: UUID) -> list[JournalEntry]:
        self.require_tenant(tenant_id)
        entries = list(self.journal_entries.values())
        for entry in entries:
            entry.lines = self.list_journal_lines(tenant_id, entry.id)
        return sorted(entries, key=lambda item: item.entry_at)

    def get_journal_by_origin(
        self, tenant_id: UUID, origin_source: str, origin_id: UUID, kind: str
    ) -> JournalEntry | None:
        self.require_tenant(tenant_id)
        for entry in self.journal_entries.values():
            if (
                entry.origin_source == origin_source
                and entry.origin_id == origin_id
                and entry.kind == kind
            ):
                entry.lines = self.list_journal_lines(tenant_id, entry.id)
                return entry
        return None

    def _period_key(self, date_from: Any, date_to: Any) -> tuple[Any, Any]:
        from datetime import date as date_cls

        def _as_date(value: Any) -> Any:
            if isinstance(value, date_cls):
                return value
            return date_cls.fromisoformat(str(value)[:10])

        return (_as_date(date_from), _as_date(date_to))

    def list_accounting_periods(self, tenant_id: UUID) -> list[AccountingPeriod]:
        self.require_tenant(tenant_id)
        return sorted(
            [item for item in self.accounting_periods.values() if item.tenant_id == tenant_id],
            key=lambda item: (item.date_from, item.date_to),
        )

    def get_accounting_period(
        self, tenant_id: UUID, *, date_from: Any, date_to: Any
    ) -> AccountingPeriod | None:
        self.require_tenant(tenant_id)
        return self.accounting_periods.get(self._period_key(date_from, date_to))

    def close_accounting_period(
        self,
        tenant_id: UUID,
        *,
        date_from: Any,
        date_to: Any,
        closed_by_name: str = "",
    ) -> AccountingPeriod:
        from datetime import UTC, datetime

        self.require_tenant(tenant_id)
        key = self._period_key(date_from, date_to)
        if key[0] > key[1]:
            raise ValueError("bad_period_range")
        existing = self.accounting_periods.get(key)
        now = datetime.now(UTC)
        if existing is None:
            period = AccountingPeriod(
                id=uuid4(),
                tenant_id=tenant_id,
                date_from=key[0],
                date_to=key[1],
                status="closed",
                closed_at=now,
                closed_by_name=(closed_by_name or "").strip() or None,
            )
        else:
            period = AccountingPeriod(
                id=existing.id,
                tenant_id=tenant_id,
                date_from=key[0],
                date_to=key[1],
                status="closed",
                closed_at=now,
                closed_by_name=(closed_by_name or "").strip() or existing.closed_by_name,
            )
        self.accounting_periods[key] = period
        return period

    def reopen_accounting_period(
        self, tenant_id: UUID, *, date_from: Any, date_to: Any
    ) -> AccountingPeriod:
        self.require_tenant(tenant_id)
        key = self._period_key(date_from, date_to)
        existing = self.accounting_periods.get(key)
        if existing is None:
            raise ValueError("period_not_found")
        period = AccountingPeriod(
            id=existing.id,
            tenant_id=tenant_id,
            date_from=key[0],
            date_to=key[1],
            status="open",
            closed_at=None,
            closed_by_name=None,
        )
        self.accounting_periods[key] = period
        return period

    def list_purchases(self, tenant_id: UUID) -> list[PurchaseReceipt]:
        self.require_tenant(tenant_id)
        return [item for item in self.purchases if item.tenant_id == tenant_id]

    def receive_purchase(
        self,
        tenant_id: UUID,
        variant_sku: str,
        quantity: int,
        unit_cost: Decimal,
        currency: str = "BOB",
        payment_method: str = "cash",
        supplier_id: UUID | None = None,
        received_at: Any = None,
        purchase_order_id: UUID | None = None,
    ) -> PurchaseReceipt:
        from datetime import UTC, datetime

        from factory_os.domain.ledger import remember_purchase

        self.require_tenant(tenant_id)
        if quantity < 1 or unit_cost <= 0:
            raise ValueError("bad_purchase")
        method = (payment_method or "cash").strip().lower() or "cash"
        if method not in {"cash", "credit"}:
            raise ValueError("bad_payment_method")
        resolved_order: UUID | None = None
        if purchase_order_id is not None:
            linked = self.get_purchase_order(tenant_id, purchase_order_id)
            if linked is None:
                raise KeyError(purchase_order_id)
            resolved_order = linked.id
        resolved_supplier: UUID | None = None
        if supplier_id is not None:
            supplier = self.get_supplier(tenant_id, supplier_id)
            if supplier is None:
                raise KeyError(supplier_id)
            resolved_supplier = supplier.id
        when = received_at if isinstance(received_at, datetime) else datetime.now(UTC)
        if when.tzinfo is None:
            when = when.replace(tzinfo=UTC)
        self.adjust_stock(tenant_id, variant_sku, quantity)
        if resolved_supplier is not None:
            record = self.get_variant(tenant_id, variant_sku)
            if record is not None and record.supplier_id is None:
                self.set_variant_supplier(tenant_id, variant_sku, resolved_supplier)
        receipt = PurchaseReceipt(
            id=uuid4(),
            tenant_id=tenant_id,
            variant_sku=variant_sku,
            quantity=quantity,
            unit_cost=unit_cost,
            currency=currency or "BOB",
            created_at=when,
            payment_method=method,
            supplier_id=resolved_supplier,
            received_at=when,
            purchase_order_id=resolved_order,
        )
        self.purchases.append(receipt)
        remember_purchase(self, receipt)
        return receipt

    def add_invoice_document(
        self, tenant_id: UUID, order_id: UUID, amount: Decimal, currency: str
    ) -> InvoiceDocument:
        from datetime import UTC, datetime

        self.require_tenant(tenant_id)
        document = InvoiceDocument(
            id=uuid4(),
            tenant_id=tenant_id,
            order_id=order_id,
            status="draft",
            amount=amount,
            currency=currency or "BOB",
            created_at=datetime.now(UTC),
        )
        self.invoices.append(document)
        return document

    def set_invoice_status(
        self, tenant_id: UUID, document_id: UUID, status: str, external_ref: str
    ) -> InvoiceDocument:
        self.require_tenant(tenant_id)
        if status not in {"draft", "exported", "issued", "failed"}:
            raise ValueError("bad_invoice_status")
        for document in self.invoices:
            if document.id == document_id:
                document.status = status
                document.external_ref = external_ref
                return document
        raise KeyError(document_id)

    def list_invoices(self, tenant_id: UUID) -> list[InvoiceDocument]:
        self.require_tenant(tenant_id)
        return list(self.invoices)

    def get_shop_knowledge(self, tenant_id: UUID) -> dict[str, Any] | None:
        self.require_tenant(tenant_id)
        if self.shop_knowledge is None:
            return None
        return dict(self.shop_knowledge)

    def put_shop_knowledge(self, tenant_id: UUID, payload: dict[str, Any]) -> dict[str, Any]:
        from factory_os.domain.knowledge import merge_shop_pack, sanitize_shop_pack

        self.require_tenant(tenant_id)
        stored = merge_shop_pack(self.shop_knowledge, sanitize_shop_pack(payload))
        self.shop_knowledge = stored
        return dict(stored)

    def get_analytics_thresholds(self, tenant_id: UUID) -> AnalyticsThresholds:
        self.require_tenant(tenant_id)
        if self.analytics_thresholds is None:
            return AnalyticsThresholds()
        return self.analytics_thresholds

    def put_analytics_thresholds(
        self, tenant_id: UUID, thresholds: AnalyticsThresholds
    ) -> AnalyticsThresholds:
        self.require_tenant(tenant_id)
        if not isinstance(thresholds, AnalyticsThresholds):
            raise ValueError("bad_thresholds")
        self.analytics_thresholds = thresholds
        return thresholds

    def analytics_digest_sent(self, tenant_id: UUID, business_date: date) -> bool:
        self.require_tenant(tenant_id)
        return business_date in self.analytics_digest_log

    def record_analytics_digest(
        self,
        tenant_id: UUID,
        business_date: date,
        alert_type_count: int,
        sent_at: datetime,
    ) -> None:
        self.require_tenant(tenant_id)
        self.analytics_digest_log[business_date] = {
            "sent_at": sent_at,
            "alert_type_count": int(alert_type_count),
        }
