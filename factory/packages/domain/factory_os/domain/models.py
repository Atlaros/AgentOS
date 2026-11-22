from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

PILOT_TENANT_ID = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")

# Same row, two commercial states. Reserva holds the garment while the QR is unpaid.
ORDER_RESERVED = "reserved"
ORDER_PLACED = "placed"
ORDER_STATUSES = frozenset({ORDER_RESERVED, ORDER_PLACED, "open", "cancelled", "delivered"})


class EmployeeRole(str, Enum):
    """Runtime employees. Coordinador is WHO (`choose_employee`), not this enum."""

    SALES = "sales"
    COBROS = "collections"
    OPS = "ops"
    POSTVENTA = "postventa"
    INVENTORY = "inventory"
    CATALOG_ADMIN = "catalog_admin"
    ACCOUNTING = "accounting"
    ANALYST = "analyst"
    SUPPLIERS = "suppliers"


class ConversationStage(str, Enum):
    NEW = "new"
    DISCOVERY = "discovery"
    NEED_IDENTIFIED = "need_identified"
    RECOMMENDATION = "recommendation"
    CONSIDERATION = "consideration"
    OBJECTION = "objection"
    READY_TO_BUY = "ready_to_buy"
    CHECKOUT = "checkout"
    PURCHASED = "purchased"
    SUPPORT = "support"
    POST_SALE = "post_sale"


class NextAction(str, Enum):
    ANSWER = "answer"
    ASK_DISCOVERY_QUESTION = "ask_discovery_question"
    SEARCH_CATALOG = "search_catalog"
    RECOMMEND = "recommend"
    COMPARE = "compare"
    HANDLE_OBJECTION = "handle_objection"
    REQUEST_CONFIRMATION = "request_confirmation"
    CREATE_ORDER = "create_order"
    ADD_TO_CART = "add_to_cart"
    HANDOFF = "handoff"
    ESCALATE = "escalate"


class PaymentStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    EXPIRED = "expired"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class CatalogHit:
    product_sku: str
    variant_sku: str
    name: str
    description: str
    category: str
    attributes: dict[str, Any]
    price: Decimal
    currency: str
    stock: int
    codigo: str
    score: float


@dataclass
class Customer:
    id: UUID
    tenant_id: UUID
    wa_number: str
    name: str | None = None
    address: str | None = None


@dataclass
class CustomerNote:
    id: UUID
    tenant_id: UUID
    customer_id: UUID
    body: str
    created_at: datetime | None = None


@dataclass
class Reminder:
    id: UUID
    tenant_id: UUID
    customer_id: UUID
    kind: str
    body: str
    created_at: datetime | None = None
    sent_at: datetime | None = None


@dataclass
class ReportDownload:
    id: UUID
    tenant_id: UUID
    report_id: str
    period_id: str
    format: str
    actor_name: str
    date_from: datetime | None = None
    date_to: datetime | None = None
    actor_user_id: UUID | None = None
    created_at: datetime | None = None


@dataclass
class PanelUser:
    id: UUID
    tenant_id: UUID
    name: str
    email: str
    role: str
    secret_salt: str
    secret_hash: str
    active: bool = True
    created_at: datetime | None = None
    pin_salt: str | None = None
    pin_hash: str | None = None
    job_title: str = ""


@dataclass
class HumanAuditEvent:
    id: UUID
    tenant_id: UUID
    actor_name: str
    actor_role: str
    method: str
    path: str
    actor_id: UUID | None = None
    created_at: datetime | None = None


@dataclass
class OrderItem:
    variant_sku: str
    name: str
    quantity: int
    unit_price: Decimal
    currency: str
    options: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Order:
    id: UUID
    tenant_id: UUID
    customer_id: UUID
    items: list[OrderItem]
    status: str = "open"
    public_number: str | None = None
    delivered_at: datetime | None = None
    delivered_by: str | None = None
    created_at: datetime | None = None
    discount_amount: Decimal = Decimal("0")
    hold_minutes: int = 15
    origin: str = "agent"  # agent | counter
    table_label: str = ""
    fulfill_on: date | None = None
    stock_applied: bool = False


def is_counter_order(order: object) -> bool:
    """Physical sale. Operated in Caja, not the chat order list."""
    return getattr(order, "origin", "agent") == "counter"


@dataclass
class Payment:
    id: UUID
    tenant_id: UUID
    order_id: UUID | None
    provider: str
    provider_ref: str
    amount: Decimal
    currency: str
    status: PaymentStatus
    qr_payload: str
    variant_sku: str = ""
    customer_id: UUID | None = None
    created_at: datetime | None = None


@dataclass
class Delivery:
    id: UUID
    tenant_id: UUID
    order_id: UUID
    address: str
    recipient_name: str


@dataclass
class CashMovement:
    id: UUID
    tenant_id: UUID
    direction: str
    amount: Decimal
    currency: str
    reason: str
    session_id: UUID | None = None
    created_at: datetime | None = None
    category: str = ""
    method: str = "cash"
    status: str = "recorded"  # recorded | voided
    recorded_by_name: str = "sistema"
    recorded_by_id: UUID | None = None
    void_reason: str | None = None
    voided_by_name: str | None = None
    voided_by_id: UUID | None = None
    voided_at: datetime | None = None
    ticket_id: UUID | None = None


@dataclass
class CashAttachment:
    """Metadata only; file bytes live on disk under CASH_ATTACHMENTS_DIR."""

    id: UUID
    tenant_id: UUID
    movement_id: UUID
    filename: str
    content_type: str
    size_bytes: int
    storage_key: str
    uploaded_by_name: str = "sistema"
    created_at: datetime | None = None


@dataclass
class MediaAsset:
    """Metadata only; bytes live on disk under MEDIA_DIR (ADR-015)."""

    id: UUID
    tenant_id: UUID
    kind: str
    mime: str
    size_bytes: int
    storage_key: str
    origin: str
    thumb_key: str | None = None
    medium_key: str | None = None
    uploaded_by: str | None = None
    provider_ref: str | None = None
    created_at: datetime | None = None


@dataclass
class ProductMedia:
    """Catalog gallery link: product_sku ↔ media asset (ADR-015)."""

    id: UUID
    tenant_id: UUID
    product_sku: str
    asset_id: UUID
    is_primary: bool = False
    sort_order: int = 0
    created_at: datetime | None = None


@dataclass
class ConversationMedia:
    """Chat ↔ media link (ADR-015 Fase C). Parallel to message tuples."""

    id: UUID
    tenant_id: UUID
    conversation_id: UUID
    asset_id: UUID | None
    direction: str
    status: str
    kind: str
    provider_ref: str | None = None
    message_index: int | None = None
    mime: str | None = None
    filename: str | None = None
    size_bytes: int | None = None
    error: str | None = None
    uploaded_by: str | None = None
    created_at: datetime | None = None
    transcript_text: str | None = None
    summary_text: str | None = None
    enrichment_status: str = "none"
    enrichment_error: str | None = None


@dataclass
class EntityMedia:
    """Order / purchase-order ↔ media link (ADR-015 Fase E)."""

    id: UUID
    tenant_id: UUID
    entity_type: str
    entity_id: UUID
    asset_id: UUID
    filename: str
    kind: str
    mime: str
    size_bytes: int
    note: str | None = None
    uploaded_by: str | None = None
    created_at: datetime | None = None


@dataclass
class CashSaleLine:
    variant_sku: str
    name: str
    quantity: int
    unit_price: Decimal
    currency: str
    line_total: Decimal
    options: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class CashSaleTicket:
    id: UUID
    tenant_id: UUID
    number: str
    status: str
    method: str
    total: Decimal
    currency: str
    lines: list[CashSaleLine] = field(default_factory=list)
    session_id: UUID | None = None
    movement_id: UUID | None = None
    payment_id: UUID | None = None
    provider_ref: str | None = None
    recorded_by_name: str = "sistema"
    recorded_by_id: UUID | None = None
    created_at: datetime | None = None
    order_id: UUID | None = None
    discount_amount: Decimal = Decimal("0")


@dataclass
class CashSession:
    id: UUID
    tenant_id: UUID
    status: str
    opening_float: Decimal
    currency: str
    opened_by_name: str
    opened_by_id: UUID | None = None
    opened_at: datetime | None = None
    closed_at: datetime | None = None
    closed_by_name: str | None = None
    closed_by_id: UUID | None = None
    counted_cash: Decimal | None = None
    expected_cash: Decimal | None = None
    difference: Decimal | None = None
    close_note: str | None = None


class InvoiceStatus(str, Enum):
    DRAFT = "draft"
    EXPORTED = "exported"
    ISSUED = "issued"
    FAILED = "failed"


@dataclass
class LedgerEntry:
    id: UUID
    tenant_id: UUID
    source: str
    source_id: UUID
    direction: str
    amount: Decimal
    currency: str
    created_at: datetime | None = None
    status: str = "recorded"


@dataclass
class ChartAccount:
    id: UUID
    tenant_id: UUID
    code: str
    name: str
    account_type: str
    is_system: bool = True
    active: bool = True
    created_at: datetime | None = None


@dataclass
class JournalLine:
    id: UUID
    tenant_id: UUID
    entry_id: UUID
    account_id: UUID
    direction: str
    amount: Decimal
    currency: str
    account_code: str | None = None


@dataclass
class JournalEntry:
    id: UUID
    tenant_id: UUID
    entry_at: datetime
    origin_source: str
    origin_id: UUID
    kind: str
    memo: str = ""
    reverses_entry_id: UUID | None = None
    lines: list[JournalLine] = field(default_factory=list)
    created_at: datetime | None = None


@dataclass
class AccountingPeriod:
    id: UUID
    tenant_id: UUID
    date_from: date
    date_to: date
    status: str
    closed_at: datetime | None = None
    closed_by_name: str | None = None


@dataclass
class Supplier:
    """Preferred vendor for replenishment (ADR-012). Soft-deactivate only."""

    id: UUID
    tenant_id: UUID
    name: str
    contact_name: str = ""
    phone: str = ""
    whatsapp: str = ""
    email: str = ""
    notes: str = ""
    payment_terms: str = "cash"
    lead_time_days: int = 0
    active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class PurchaseOrderLine:
    id: UUID
    tenant_id: UUID
    purchase_order_id: UUID
    variant_sku: str
    quantity_ordered: int
    quantity_received: int = 0
    unit_cost: Decimal | None = None
    currency: str = "BOB"


@dataclass
class PurchaseOrder:
    """Supplier purchase order (ADR-012)."""

    id: UUID
    tenant_id: UUID
    supplier_id: UUID
    status: str = "draft"
    notes: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None
    lines: list[PurchaseOrderLine] = field(default_factory=list)
    payment_status: str = "unpaid"
    amount_paid: Decimal = Decimal("0")


@dataclass
class PurchaseReceipt:
    id: UUID
    tenant_id: UUID
    variant_sku: str
    quantity: int
    unit_cost: Decimal
    currency: str
    created_at: datetime | None = None
    payment_method: str = "cash"
    supplier_id: UUID | None = None
    received_at: datetime | None = None
    purchase_order_id: UUID | None = None


@dataclass
class InvoiceDocument:
    id: UUID
    tenant_id: UUID
    order_id: UUID | None
    status: str
    amount: Decimal
    currency: str
    external_ref: str = ""
    created_at: datetime | None = None


@dataclass
class HandoffFolder:
    """Facts for the next employee. Not a chat dump. Payment truth stays in Postgres."""

    to: EmployeeRole | None = None
    from_role: EmployeeRole | None = None
    order_id: UUID | None = None
    payment_state: str | None = None
    need: str | None = None
    pending: str | None = None
    reason: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "to": self.to.value if self.to else None,
            "from_role": self.from_role.value if self.from_role else None,
            "order_id": str(self.order_id) if self.order_id else None,
            "payment_state": self.payment_state,
            "need": self.need,
            "pending": self.pending,
            "reason": self.reason,
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any] | None) -> HandoffFolder:
        data = payload or {}
        to = data.get("to")
        from_role = data.get("from_role")
        return cls(
            to=EmployeeRole(to) if to else None,
            from_role=EmployeeRole(from_role) if from_role else None,
            order_id=UUID(str(data["order_id"])) if data.get("order_id") else None,
            payment_state=data.get("payment_state"),
            need=data.get("need"),
            pending=data.get("pending"),
            reason=data.get("reason"),
        )


@dataclass
class WorkingState:
    considered_variant_sku: str | None = None
    last_hits: list[dict[str, Any]] = field(default_factory=list)
    order_id: UUID | None = None
    payment_id: UUID | None = None
    provider_ref: str | None = None
    last_employee: EmployeeRole | None = None
    folder: HandoffFolder = field(default_factory=HandoffFolder)
    human_takeover: bool = False
    needs_human: bool = False
    owner_notified: bool = False
    stage: ConversationStage = ConversationStage.NEW
    customer_need: str | None = None
    current_objection: str | None = None
    last_action: str | None = None
    last_skill: str | None = None
    pending_action: str | None = None
    discovery_asked: bool = False
    budget_max: Decimal | None = None
    size: str | None = None
    color: str | None = None
    occasion: str | None = None
    style: str | None = None
    preference_provenance: dict[str, str] = field(default_factory=dict)
    cart: list[dict[str, Any]] = field(default_factory=list)
    channel: str = "whatsapp"
    incident: str | None = None
    graph_node: str | None = None
    fulfill_on: str = ""
    chat_resolution: str = ""

    @property
    def handoff(self) -> EmployeeRole | None:
        return self.folder.to

    @handoff.setter
    def handoff(self, role: EmployeeRole | None) -> None:
        self.folder.to = role

    def pass_to(
        self,
        to: EmployeeRole | None,
        *,
        from_role: EmployeeRole | None = None,
        pending: str | None = None,
        reason: str | None = None,
        payment_state: str | None = None,
        need: str | None = None,
    ) -> None:
        self.folder = HandoffFolder(
            to=to,
            from_role=from_role,
            order_id=self.order_id,
            payment_state=payment_state,
            need=self.customer_need if need is None else need,
            pending=pending,
            reason=reason,
        )
        self.pending_action = pending

    def to_json(self) -> dict[str, Any]:
        return {
            "considered_variant_sku": self.considered_variant_sku,
            "last_hits": list(self.last_hits),
            "order_id": str(self.order_id) if self.order_id else None,
            "payment_id": str(self.payment_id) if self.payment_id else None,
            "provider_ref": self.provider_ref,
            "last_employee": self.last_employee.value if self.last_employee else None,
            "handoff": self.handoff.value if self.handoff else None,
            "folder": self.folder.to_json(),
            "human_takeover": self.human_takeover,
            "needs_human": self.needs_human,
            "owner_notified": self.owner_notified,
            "stage": self.stage.value,
            "customer_need": self.customer_need,
            "current_objection": self.current_objection,
            "last_action": self.last_action,
            "last_skill": self.last_skill,
            "pending_action": self.pending_action,
            "discovery_asked": self.discovery_asked,
            "budget_max": str(self.budget_max) if self.budget_max is not None else None,
            "size": self.size,
            "color": self.color,
            "occasion": self.occasion,
            "style": self.style,
            "preference_provenance": dict(self.preference_provenance),
            "cart": list(self.cart),
            "channel": self.channel,
            "incident": self.incident,
            "graph_node": self.graph_node,
            "fulfill_on": self.fulfill_on,
            "chat_resolution": self.chat_resolution,
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any] | None) -> WorkingState:
        data = payload or {}
        last = data.get("last_employee")
        stage = data.get("stage") or ConversationStage.NEW.value
        hits = data.get("last_hits") or []
        folder = HandoffFolder.from_json(data.get("folder") if isinstance(data.get("folder"), dict) else None)
        if folder.to is None and data.get("handoff"):
            folder.to = EmployeeRole(str(data["handoff"]))
        if folder.order_id is None and data.get("order_id"):
            folder.order_id = UUID(str(data["order_id"]))
        if folder.pending is None:
            folder.pending = data.get("pending_action")
        if folder.need is None:
            folder.need = data.get("customer_need")
        return cls(
            considered_variant_sku=data.get("considered_variant_sku"),
            last_hits=[hit for hit in hits if isinstance(hit, dict)],
            order_id=UUID(data["order_id"]) if data.get("order_id") else None,
            payment_id=UUID(data["payment_id"]) if data.get("payment_id") else None,
            provider_ref=data.get("provider_ref"),
            last_employee=EmployeeRole(last) if last else None,
            folder=folder,
            human_takeover=bool(data.get("human_takeover")),
            needs_human=bool(data.get("needs_human")),
            owner_notified=bool(data.get("owner_notified")),
            stage=ConversationStage(stage),
            customer_need=data.get("customer_need"),
            current_objection=data.get("current_objection"),
            last_action=data.get("last_action"),
            last_skill=data.get("last_skill"),
            pending_action=data.get("pending_action") if data.get("pending_action") is not None else folder.pending,
            discovery_asked=bool(data.get("discovery_asked")),
            budget_max=_optional_decimal(data.get("budget_max")),
            size=data.get("size"),
            color=data.get("color"),
            occasion=data.get("occasion"),
            style=data.get("style"),
            preference_provenance={
                str(k): str(v)
                for k, v in (data.get("preference_provenance") or {}).items()
                if isinstance(k, str)
            },
            cart=[item for item in (data.get("cart") or []) if isinstance(item, dict)],
            channel=str(data.get("channel") or "whatsapp"),
            incident=data.get("incident"),
            graph_node=str(data["graph_node"]) if data.get("graph_node") else None,
            fulfill_on=str(data.get("fulfill_on") or ""),
            chat_resolution=str(data.get("chat_resolution") or ""),
        )


def _optional_decimal(raw: object) -> Decimal | None:
    if raw is None or raw == "":
        return None
    try:
        return Decimal(str(raw))
    except Exception:
        return None


@dataclass
class Conversation:
    id: UUID
    tenant_id: UUID
    customer_id: UUID
    messages: list[tuple[str, str]] = field(default_factory=list)
    state: WorkingState = field(default_factory=WorkingState)
    summary_text: str | None = None
    summary_msg_count: int = 0
    outcome: str | None = None
    outcome_reason: str | None = None
    source_kind: str | None = None
    live_code: str | None = None
    closed_at: datetime | None = None
    last_message_at: datetime | None = None
    # Per-turn only; never persisted in working_state JSON.
    turn_idle_reopen: bool = False
