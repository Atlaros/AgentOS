"""Walk-in cash sales: ticket + stock, no chat Order (ADR-009 T3/T7)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol
from uuid import UUID, uuid4

from factory_os.domain.catalog import (
    STOP,
    expand_query,
    hit_to_dict,
    normalize,
    score_variant,
    search_catalog,
    tokenize,
)
from factory_os.domain.models import (
    CashSaleLine,
    CashSaleTicket,
    CatalogHit,
    Order,
    OrderItem,
    Payment,
)
from factory_os.domain.seed import product_code_tokens
from factory_os.domain.stock import consume_stock, release_stock
from factory_os.domain.store import CommerceStore, VariantRecord


class CashSaleError(Exception):
    def __init__(self, code: str, status: int = 400) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class RequestedLine:
    variant_sku: str
    quantity: int
    option_ids: tuple[str, ...] = ()


class CashSaleStore(Protocol):
    def get_open_cash_session(self, tenant_id: UUID) -> Any: ...
    def get_variant(self, tenant_id: UUID, variant_sku: str) -> VariantRecord | None: ...
    def held_variant_skus(self, tenant_id: UUID) -> set[str]: ...
    def set_variant_availability(
        self,
        tenant_id: UUID,
        variant_sku: str,
        *,
        available: bool,
        stock: int | None = None,
    ) -> VariantRecord: ...
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
    ) -> Any: ...
    def create_cash_sale_ticket(self, tenant_id: UUID, ticket: CashSaleTicket) -> CashSaleTicket: ...
    def set_cash_sale_movement(
        self, tenant_id: UUID, ticket_id: UUID, movement_id: UUID
    ) -> CashSaleTicket: ...
    def get_cash_sale_ticket(self, tenant_id: UUID, ticket_id: UUID) -> CashSaleTicket | None: ...
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
    def get_payment(self, tenant_id: UUID, payment_id: UUID) -> Payment | None: ...
    def set_payment_status(
        self,
        tenant_id: UUID,
        payment_id_or_ref: UUID | str,
        status: str,
    ) -> Payment: ...
    def list_cash_sale_tickets(
        self, tenant_id: UUID, session_id: UUID | None = None
    ) -> list[CashSaleTicket]: ...
    def get_or_create_customer(self, tenant_id: UUID, wa_number: str) -> Any: ...
    def create_order(
        self,
        tenant_id: UUID,
        customer_id: UUID,
        item: OrderItem | None = None,
        *,
        status: str = "open",
        items: list[OrderItem] | None = None,
        origin: str = "agent",
        table_label: str = "",
        discount_amount: Decimal = Decimal("0"),
    ) -> Order: ...
    def get_order(self, tenant_id: UUID, order_id: UUID) -> Order | None: ...
    def set_order_status(
        self, tenant_id: UUID, order_id: UUID, status: str, *, delivered_by: str = "owner"
    ) -> Order: ...
    def list_orders(self, tenant_id: UUID) -> list[Order]: ...


def new_ticket_number() -> str:
    """Public readable walk-in ticket id, e.g. TK-A1B2C3D4."""
    return f"TK-{uuid4().hex[:8].upper()}"


def _parse_exact_price(query: str) -> Decimal | None:
    text = (query or "").strip().replace(",", ".")
    if not text:
        return None
    try:
        amount = Decimal(text)
    except InvalidOperation:
        return None
    if amount <= 0:
        return None
    return amount.quantize(Decimal("0.01"))


def _hit_from_record(record: VariantRecord, score: float) -> CatalogHit:
    return CatalogHit(
        product_sku=record.product_sku,
        variant_sku=record.variant_sku,
        name=record.name,
        description=record.description,
        category=record.category,
        attributes=dict(record.attributes),
        price=record.price,
        currency=record.currency,
        stock=record.stock,
        codigo=str(record.attributes.get("codigo") or ""),
        score=float(score),
    )


def search_cash_catalog(
    store: CommerceStore,
    tenant_id: UUID,
    query: str,
    *,
    limit: int = 40,
) -> list[dict[str, Any]]:
    """Drawer search by codigo, description, or exact price.

    Reuses ``search_catalog`` for ranking, then supplements with undiversified
    lexical matches and exact-price hits so every sellable SKU is reachable.
    """
    q = (query or "").strip()
    if not q:
        return []
    store.require_tenant(tenant_id)
    from factory_os.domain.order_hold import release_expired_unpaid_orders

    release_expired_unpaid_orders(store, tenant_id)
    held = store.held_variant_skus(tenant_id)
    primary = {
        hit.variant_sku: hit
        for hit in search_catalog(
            store,
            tenant_id,
            q,
            limit=limit,
            include_test_only=True,
        )
    }
    price_q = _parse_exact_price(q)
    raw_tokens = (tokenize(q) - STOP) | set(product_code_tokens(q))
    tokens = expand_query(raw_tokens)
    query_norm = normalize(q)
    for record in store.iter_variants():
        if record.attributes.get("disabled") or record.stock < 1:
            continue
        if record.variant_sku in held:
            continue
        lexical = score_variant(tokens, record, query_norm) if tokens else 0.0
        exact_price = price_q is not None and record.price == price_q
        if lexical <= 0 and not exact_price:
            continue
        if record.variant_sku in primary:
            continue
        primary[record.variant_sku] = _hit_from_record(
            record, 12.0 if exact_price else lexical
        )
    ranked = sorted(
        primary.values(),
        key=lambda hit: (-hit.score, hit.price, hit.variant_sku),
    )
    return [hit_to_dict(hit) for hit in ranked[:limit]]


def _requested_lines(lines: list[RequestedLine | tuple]) -> list[RequestedLine]:
    requested: list[RequestedLine] = []
    for raw in lines:
        if isinstance(raw, RequestedLine):
            requested.append(raw)
            continue
        sku = raw[0]
        quantity = int(raw[1])
        option_ids = tuple(str(item) for item in raw[2]) if len(raw) > 2 else ()
        requested.append(RequestedLine(str(sku), quantity, option_ids))
    return requested


def _resolve_lines(
    store: CashSaleStore,
    tenant_id: UUID,
    lines: list[RequestedLine | tuple],
) -> list[CashSaleLine]:
    requested = _requested_lines(lines)
    if not requested:
        raise CashSaleError("empty")
    grouped: dict[tuple[str, tuple[str, ...]], int] = {}
    order: list[tuple[str, tuple[str, ...]]] = []
    per_sku: dict[str, int] = {}
    for line in requested:
        sku = (line.variant_sku or "").strip()
        if not sku or line.quantity < 1:
            raise CashSaleError("bad_quantity")
        option_ids = tuple(dict.fromkeys(item.strip() for item in line.option_ids if item.strip()))
        key = (sku, option_ids)
        if key not in grouped:
            order.append(key)
        grouped[key] = grouped.get(key, 0) + line.quantity
        per_sku[sku] = per_sku.get(sku, 0) + line.quantity
    held = set(store.held_variant_skus(tenant_id))
    records: dict[str, VariantRecord] = {}
    for sku, quantity in per_sku.items():
        record = store.get_variant(tenant_id, sku)
        if record is None:
            raise CashSaleError("unknown_variant")
        if record.attributes.get("disabled"):
            raise CashSaleError("disabled_variant", 409)
        from factory_os.domain.combos import combo_components, makeable_units

        from factory_os.domain.stock import tracks_stock

        if combo_components(record):
            if sku in held or makeable_units(store, tenant_id, record, held) < quantity:
                raise CashSaleError("out_of_stock", 409)
        elif tracks_stock(record) and (record.stock < quantity or sku in held):
            raise CashSaleError("out_of_stock", 409)
        records[sku] = record
    from factory_os.domain.modifiers import selected_options

    resolved: list[CashSaleLine] = []
    for sku, option_ids in order:
        record = records[sku]
        try:
            options, delta = selected_options(store, tenant_id, option_ids)
        except ValueError as exc:
            raise CashSaleError(str(exc) or "unknown_modifier") from exc
        unit = (Decimal(record.price) + delta).quantize(Decimal("0.01"))
        if unit < 0:
            raise CashSaleError("bad_price")
        quantity = grouped[(sku, option_ids)]
        resolved.append(
            CashSaleLine(
                variant_sku=record.variant_sku,
                name=record.name,
                quantity=quantity,
                unit_price=unit,
                currency=record.currency or "BOB",
                line_total=(unit * quantity).quantize(Decimal("0.01")),
                options=options,
            )
        )
    return resolved


def _split_discount(subtotal: Decimal, raw: Decimal | str | None) -> tuple[Decimal, Decimal]:
    """Catalog subtotal minus one ticket discount. The discount cannot exceed it."""
    base = subtotal.quantize(Decimal("0.01"))
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return Decimal("0.00"), base
    try:
        discount = Decimal(str(raw).strip()).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError) as exc:
        raise CashSaleError("bad_discount") from exc
    if discount < 0:
        raise CashSaleError("bad_discount")
    if discount > base:
        raise CashSaleError("discount_exceeds")
    return discount, (base - discount).quantize(Decimal("0.01"))


def ticket_payload(ticket: CashSaleTicket, *, qr: str | None = None) -> dict[str, Any]:
    """Serialize a walk-in ticket for panel API responses."""
    return {
        "id": str(ticket.id),
        "number": ticket.number,
        "status": ticket.status,
        "method": ticket.method,
        "total": str(ticket.total),
        "discount_amount": str(ticket.discount_amount),
        "currency": ticket.currency,
        "lines": [
            {
                "variant_sku": line.variant_sku,
                "name": line.name,
                "quantity": line.quantity,
                "unit_price": str(line.unit_price),
                "currency": line.currency,
                "line_total": str(line.line_total),
                **({"options": list(line.options)} if line.options else {}),
            }
            for line in ticket.lines
        ],
        "movement_id": str(ticket.movement_id) if ticket.movement_id else None,
        "session_id": str(ticket.session_id) if ticket.session_id else None,
        "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
        "recorded_by_name": ticket.recorded_by_name,
        "recorded_by_id": str(ticket.recorded_by_id) if ticket.recorded_by_id else None,
        "order_id": str(ticket.order_id) if ticket.order_id else None,
        "payment_id": str(ticket.payment_id) if ticket.payment_id else None,
        "provider_ref": ticket.provider_ref or None,
        "qr": qr,
    }


def sum_session_qr_in(tickets: list[CashSaleTicket]) -> Decimal:
    """Sum recorded walk-in QR tickets for a session (informational; not drawer cash)."""
    total = sum(
        (
            ticket.total
            for ticket in tickets
            if ticket.status == "recorded" and (ticket.method or "").lower() == "qr"
        ),
        Decimal("0"),
    )
    return total.quantize(Decimal("0.01"))


COUNTER_CUSTOMER_WA = "internal:counter"


def _counter_customer_id(store: CashSaleStore, tenant_id: UUID) -> UUID:
    customer = store.get_or_create_customer(tenant_id, COUNTER_CUSTOMER_WA)
    return customer.id


def _record_counter_order(
    store: CashSaleStore,
    tenant_id: UUID,
    lines: list[CashSaleLine],
    *,
    status: str,
    table_label: str,
    discount_amount: Decimal = Decimal("0"),
) -> Order:
    items = [
        OrderItem(
            variant_sku=line.variant_sku,
            name=line.name,
            quantity=line.quantity,
            unit_price=line.unit_price,
            currency=line.currency,
            options=list(line.options),
        )
        for line in lines
    ]
    return store.create_order(
        tenant_id,
        _counter_customer_id(store, tenant_id),
        status=status,
        items=items,
        origin="counter",
        table_label=table_label,
        discount_amount=discount_amount,
    )


def _lines_from_order(order: Order) -> list[CashSaleLine]:
    resolved: list[CashSaleLine] = []
    for item in order.items:
        unit = Decimal(item.unit_price).quantize(Decimal("0.01"))
        quantity = int(item.quantity)
        resolved.append(
            CashSaleLine(
                variant_sku=item.variant_sku,
                name=item.name,
                quantity=quantity,
                unit_price=unit,
                currency=item.currency or "BOB",
                line_total=(unit * quantity).quantize(Decimal("0.01")),
                options=list(getattr(item, "options", None) or []),
            )
        )
    return resolved


def tab_payload(order: Order) -> dict[str, Any]:
    """Serialize a counter order for the cash desk."""
    return {
        "id": str(order.id),
        "origin": order.origin,
        "status": order.status,
        "table_label": order.table_label,
        "public_number": order.public_number,
        "items": [
            {
                "variant_sku": item.variant_sku,
                "name": item.name,
                "quantity": item.quantity,
                "unit_price": str(item.unit_price),
                "currency": item.currency,
                "options": list(getattr(item, "options", None) or []),
            }
            for item in order.items
        ],
    }


def open_counter_tab(
    store: CashSaleStore,
    tenant_id: UUID,
    *,
    table: str,
    lines: list[tuple[str, int]],
) -> Order:
    """Note a table. Stock is held now. The drawer does not move until charge."""
    label = (table or "").strip()
    if not label:
        raise CashSaleError("table_required")
    if len(label) > 80:
        raise CashSaleError("bad_table")
    if store.get_open_cash_session(tenant_id) is None:
        raise CashSaleError("session_required", 409)
    resolved = _resolve_lines(store, tenant_id, lines)
    order = _record_counter_order(
        store, tenant_id, resolved, status="open", table_label=label
    )
    for line in resolved:
        consume_stock(store, tenant_id, line.variant_sku, line.quantity)
    return order


def cancel_counter_tab(store: CashSaleStore, tenant_id: UUID, order_id: UUID) -> Order:
    """Cancel an open table and return the held stock. No drawer movement."""
    order = _open_counter_order(store, tenant_id, order_id)
    for item in order.items:
        release_stock(store, tenant_id, item.variant_sku, item.quantity)
    return store.set_order_status(tenant_id, order.id, "cancelled")


def charge_counter_tab(
    store: CashSaleStore,
    tenant_id: UUID,
    order_id: UUID,
    *,
    method: str,
    recorded_by_name: str,
    recorded_by_id: UUID | None = None,
    discount_amount: Decimal | str | None = None,
) -> CashSaleTicket:
    """Charge an open table. Stock was already held, so it is not subtracted again."""
    from datetime import UTC, datetime

    method_clean = (method or "cash").strip().lower() or "cash"
    if method_clean != "cash":
        raise CashSaleError("bad_method")
    session = store.get_open_cash_session(tenant_id)
    if session is None:
        raise CashSaleError("session_required", 409)
    order = _open_counter_order(store, tenant_id, order_id)
    resolved = _lines_from_order(order)
    if not resolved:
        raise CashSaleError("empty")
    subtotal = sum((line.line_total for line in resolved), Decimal("0"))
    discount, total = _split_discount(subtotal, discount_amount)
    if discount > 0:
        store.replace_order_items(tenant_id, order.id, order.items, discount_amount=discount)
    ticket = CashSaleTicket(
        id=uuid4(),
        tenant_id=tenant_id,
        number=new_ticket_number(),
        status="recorded",
        method=method_clean,
        total=total,
        currency=resolved[0].currency or "BOB",
        lines=resolved,
        session_id=session.id,
        movement_id=None,
        recorded_by_name=(recorded_by_name or "sistema").strip() or "sistema",
        recorded_by_id=recorded_by_id,
        created_at=datetime.now(UTC),
        order_id=order.id,
        discount_amount=discount,
    )
    ticket = store.create_cash_sale_ticket(tenant_id, ticket)
    movement = store.record_cash(
        tenant_id,
        "in",
        total,
        ticket.currency,
        f"ticket {ticket.number}",
        category="venta",
        method=method_clean,
        recorded_by_name=ticket.recorded_by_name,
        recorded_by_id=recorded_by_id,
        ticket_id=ticket.id,
    )
    ticket = store.set_cash_sale_movement(tenant_id, ticket.id, movement.id)
    store.set_order_status(tenant_id, order.id, "placed")
    from factory_os.domain.journal_cogs import post_cogs_for_ticket

    post_cogs_for_ticket(store, ticket)  # type: ignore[arg-type]
    return ticket


def list_open_counter_tabs(store: CashSaleStore, tenant_id: UUID) -> list[Order]:
    return [
        order
        for order in store.list_orders(tenant_id)
        if order.origin == "counter" and order.status == "open"
    ]


def _open_counter_order(store: CashSaleStore, tenant_id: UUID, order_id: UUID) -> Order:
    order = store.get_order(tenant_id, order_id)
    if order is None or order.origin != "counter":
        raise CashSaleError("unknown_tab", 404)
    if order.status != "open":
        raise CashSaleError("not_open", 409)
    return order


def create_walkin_sale(
    store: CashSaleStore,
    tenant_id: UUID,
    *,
    method: str,
    lines: list[tuple[str, int]],
    recorded_by_name: str,
    recorded_by_id: UUID | None = None,
    discount_amount: Decimal | str | None = None,
) -> CashSaleTicket:
    """Create a presencial ticket, mark stock sold, and post drawer inflow."""
    from datetime import UTC, datetime

    method_clean = (method or "cash").strip().lower() or "cash"
    if method_clean != "cash":
        raise CashSaleError("bad_method")
    session = store.get_open_cash_session(tenant_id)
    if session is None:
        raise CashSaleError("session_required", 409)
    resolved = _resolve_lines(store, tenant_id, lines)
    subtotal = sum((line.line_total for line in resolved), Decimal("0"))
    discount, total = _split_discount(subtotal, discount_amount)
    order = _record_counter_order(
        store, tenant_id, resolved, status="placed", table_label="", discount_amount=discount
    )
    currency = resolved[0].currency or "BOB"
    ticket = CashSaleTicket(
        id=uuid4(),
        tenant_id=tenant_id,
        number=new_ticket_number(),
        status="recorded",
        method=method_clean,
        total=total,
        currency=currency,
        lines=list(resolved),
        session_id=session.id,
        movement_id=None,
        recorded_by_name=(recorded_by_name or "sistema").strip() or "sistema",
        recorded_by_id=recorded_by_id,
        created_at=datetime.now(UTC),
        order_id=order.id,
        discount_amount=discount,
    )
    ticket = store.create_cash_sale_ticket(tenant_id, ticket)
    for line in resolved:
        consume_stock(store, tenant_id, line.variant_sku, line.quantity)
    movement = store.record_cash(
        tenant_id,
        "in",
        total,
        currency,
        f"ticket {ticket.number}",
        category="venta",
        method=method_clean,
        recorded_by_name=ticket.recorded_by_name,
        recorded_by_id=recorded_by_id,
        ticket_id=ticket.id,
    )
    ticket = store.set_cash_sale_movement(tenant_id, ticket.id, movement.id)
    from factory_os.domain.journal_cogs import post_cogs_for_ticket

    post_cogs_for_ticket(store, ticket)  # type: ignore[arg-type]
    return ticket


def create_walkin_qr_sale(
    store: CashSaleStore,
    payments: Any,
    tenant_id: UUID,
    *,
    lines: list[tuple[str, int]],
    recorded_by_name: str,
    recorded_by_id: UUID | None = None,
    discount_amount: Decimal | str | None = None,
) -> tuple[CashSaleTicket, str]:
    """Issue a pending walk-in QR ticket. Stock and drawer stay untouched until adapter confirm."""
    from datetime import UTC, datetime

    session = store.get_open_cash_session(tenant_id)
    if session is None:
        raise CashSaleError("session_required", 409)
    resolved = _resolve_lines(store, tenant_id, lines)
    subtotal = sum((line.line_total for line in resolved), Decimal("0"))
    discount, total = _split_discount(subtotal, discount_amount)
    currency = resolved[0].currency or "BOB"
    ticket = CashSaleTicket(
        id=uuid4(),
        tenant_id=tenant_id,
        number=new_ticket_number(),
        status="pending_qr",
        method="qr",
        total=total,
        currency=currency,
        lines=list(resolved),
        session_id=session.id,
        movement_id=None,
        payment_id=None,
        provider_ref=None,
        recorded_by_name=(recorded_by_name or "sistema").strip() or "sistema",
        recorded_by_id=recorded_by_id,
        created_at=datetime.now(UTC),
        discount_amount=discount,
    )
    ticket = store.create_cash_sale_ticket(tenant_id, ticket)
    issued = payments.create_qr(ticket.id.hex, total, currency)
    provider_name = str(getattr(payments, "name", "") or "fake")
    # Hold first line via pending payment.sku so concurrent cash cannot double-sell.
    hold_sku = resolved[0].variant_sku if resolved else ""
    payment = store.create_payment(
        tenant_id,
        None,
        provider_name,
        issued.provider_ref,
        total,
        currency,
        issued.qr_payload,
        variant_sku=hold_sku,
        customer_id=None,
    )
    ticket = store.link_cash_sale_payment(
        tenant_id, ticket.id, payment.id, issued.provider_ref
    )
    return ticket, issued.qr_payload


def complete_walkin_qr_if_pending(store: CashSaleStore, payment: Payment) -> bool:
    """Complete a pending walk-in QR ticket linked to this payment.

    Marks lines sold, sets status recorded, leaves order_id/movement_id unset.
    Returns True when this payment was a walk-in QR (caller should skip chat/order path).
    """
    if payment.id is None:
        return False
    ticket = store.cash_sale_ticket_for_payment(payment.tenant_id, payment.id)
    if ticket is None:
        return False
    if ticket.status != "pending_qr" or (ticket.method or "").lower() != "qr":
        return ticket.status == "recorded" and (ticket.method or "").lower() == "qr"
    for line in ticket.lines:
        consume_stock(store, payment.tenant_id, line.variant_sku, line.quantity)
    ticket = store.set_cash_sale_status(payment.tenant_id, ticket.id, "recorded")
    from factory_os.domain.journal_cogs import post_cogs_for_ticket

    post_cogs_for_ticket(store, ticket)  # type: ignore[arg-type]
    return True


def cancel_walkin_qr_pending(
    store: CashSaleStore,
    tenant_id: UUID,
    ticket_id: UUID,
) -> CashSaleTicket:
    """Void a pending walk-in QR ticket and release its payment hold."""
    ticket = store.get_cash_sale_ticket(tenant_id, ticket_id)
    if ticket is None:
        raise CashSaleError("ticket_not_found", 404)
    if ticket.status != "pending_qr" or (ticket.method or "").lower() != "qr":
        raise CashSaleError("not_pending_qr", 409)

    payment_key: UUID | str | None = ticket.payment_id
    if payment_key is None and ticket.provider_ref:
        payment_key = ticket.provider_ref
    if payment_key is not None:
        store.set_payment_status(tenant_id, payment_key, "expired")

    return store.set_cash_sale_status(tenant_id, ticket_id, "voided")


def lines_as_json(lines: list[CashSaleLine]) -> list[dict[str, Any]]:
    """JSON-friendly line payloads for Postgres JSONB."""
    return [
        {
            "variant_sku": line.variant_sku,
            "name": line.name,
            "quantity": line.quantity,
            "unit_price": str(line.unit_price),
            "currency": line.currency,
            "line_total": str(line.line_total),
            "options": list(line.options),
        }
        for line in lines
    ]


def lines_from_json(raw: Any) -> list[CashSaleLine]:
    if not raw:
        return []
    rows = raw if isinstance(raw, list) else []
    out: list[CashSaleLine] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        unit = Decimal(str(row.get("unit_price") or "0")).quantize(Decimal("0.01"))
        qty = int(row.get("quantity") or 0)
        out.append(
            CashSaleLine(
                variant_sku=str(row.get("variant_sku") or ""),
                name=str(row.get("name") or ""),
                quantity=qty,
                unit_price=unit,
                currency=str(row.get("currency") or "BOB"),
                line_total=Decimal(str(row.get("line_total") or unit * qty)).quantize(
                    Decimal("0.01")
                ),
                options=[
                    item
                    for item in (row.get("options") or [])
                    if isinstance(item, dict)
                ],
            )
        )
    return out
