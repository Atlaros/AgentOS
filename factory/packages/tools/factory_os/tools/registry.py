from __future__ import annotations

from decimal import Decimal
from typing import Any

from factory_os.contracts.employees import Identity
from factory_os.domain.catalog import hit_to_dict, search_catalog
from factory_os.domain.models import OrderItem, PaymentStatus
from factory_os.domain.seed import tokenize
from factory_os.domain.store import CommerceStore, VariantRecord
from factory_os.harness.policy import PolicyEngine
from factory_os.harness.tools import ToolRuntime, ToolSpec
from factory_os.tools.payments import FakePaymentProvider, PaymentProvider


def _drop_unpaid_reservation(store: CommerceStore, tenant_id, order_id) -> None:
    order = store.get_order(tenant_id, order_id)
    if order is None or order.status not in {"reserved", "open"}:
        return
    payment = store.payment_for_order(tenant_id, order_id)
    if payment is not None and payment.status is PaymentStatus.CONFIRMED:
        return
    store.delete_order(tenant_id, order_id)


def _items_from_cart(
    store: CommerceStore, tenant_id, cart_raw: list, *, check_stock: bool = True
) -> list[OrderItem] | dict[str, str]:
    """Catalog prices only. Merges duplicate SKUs. Rejects held or missing stock."""
    from factory_os.domain.cart_quote import merge_lines

    held = store.held_variant_skus(tenant_id) if check_stock else set()
    rough: list[dict[str, Any]] = []
    for raw in cart_raw:
        if not isinstance(raw, dict):
            continue
        sku = str(raw.get("variant_sku") or "")
        quantity = int(raw.get("quantity") or 1)
        if not sku or quantity < 1:
            return {"error": "bad_quantity"}
        rough.append({"variant_sku": sku, "quantity": quantity, "name": sku, "unit_price": "0"})
    merged = merge_lines(rough)
    if not merged:
        return {"error": "empty_cart"}
    items: list[OrderItem] = []
    for line in merged:
        record = store.get_variant(tenant_id, line.variant_sku)
        if record is None:
            return {"error": "unknown_variant"}
        if check_stock and (record.attributes.get("disabled") or record.stock < line.quantity):
            return {"error": "out_of_stock"}
        if check_stock and record.variant_sku in held:
            return {"error": "out_of_stock"}
        items.append(
            OrderItem(
                variant_sku=record.variant_sku,
                name=record.name,
                quantity=line.quantity,
                unit_price=record.price,
                currency=record.currency,
            )
        )
    return items


def build_runtime(
    store: CommerceStore,
    payments: PaymentProvider,
    invoices=None,
    channel=None,
) -> ToolRuntime:
    def catalog_search(identity: Identity, payload: dict[str, Any]) -> dict[str, Any]:
        from decimal import InvalidOperation

        raw_budget = payload.get("budget_max")
        budget_max = None
        if raw_budget is not None and raw_budget != "":
            try:
                budget_max = Decimal(str(raw_budget).replace(",", "."))
            except (InvalidOperation, ValueError):
                budget_max = None
        filters = payload.get("filters") if isinstance(payload.get("filters"), dict) else None
        hits = search_catalog(
            store,
            identity.tenant_id,
            str(payload.get("query") or ""),
            budget_max=budget_max,
            filters={str(k): str(v) for k, v in (filters or {}).items() if v},
            include_test_only=bool(payload.get("include_test_only")),
        )
        return {"hits": [hit_to_dict(hit) for hit in hits]}

    def cart_add(identity: Identity, payload: dict[str, Any]) -> dict[str, Any]:
        variant_sku = str(payload.get("variant_sku") or "")
        quantity = int(payload.get("quantity") or 1)
        record = store.get_variant(identity.tenant_id, variant_sku)
        if record is None:
            return {"error": "unknown_variant"}
        if quantity < 1:
            return {"error": "bad_quantity"}
        if record.stock < quantity:
            return {"error": "out_of_stock"}
        if record.attributes.get("disabled"):
            return {"error": "disabled_variant"}
        cart = list(payload.get("cart") or [])
        item = {
            "variant_sku": record.variant_sku,
            "product_sku": record.product_sku,
            "name": record.name,
            "quantity": quantity,
            "price": str(record.price),
            "currency": record.currency,
        }
        for existing in cart:
            if str(existing.get("variant_sku") or "") == record.variant_sku:
                existing["quantity"] = int(existing.get("quantity") or 1) + quantity
                existing["price"] = str(record.price)
                existing["name"] = record.name
                existing["currency"] = record.currency
                return {"cart": cart, "item": existing}
        cart.append(item)
        return {"cart": cart, "item": item}

    def cart_remove(identity: Identity, payload: dict[str, Any]) -> dict[str, Any]:
        variant_sku = str(payload.get("variant_sku") or "")
        cart = [item for item in list(payload.get("cart") or []) if isinstance(item, dict)]
        kept = [item for item in cart if str(item.get("variant_sku") or "") != variant_sku]
        if len(kept) == len(cart):
            return {"error": "not_in_cart"}
        return {"cart": kept}

    def order_create(identity: Identity, payload: dict[str, Any]) -> dict[str, Any]:
        from factory_os.domain.future_orders import business_today, owner_notice, parse_fulfill_on

        variant_sku = str(payload.get("variant_sku") or "")
        record = store.get_variant(identity.tenant_id, variant_sku)
        if record is None:
            return {"error": "unknown_variant"}
        quantity = int(payload.get("quantity") or 1)
        try:
            fulfill_on = parse_fulfill_on(payload.get("fulfill_on"), today=business_today())
        except ValueError as exc:
            return {"error": str(exc)}
        if fulfill_on is None:
            if record.stock < quantity:
                return {"error": "out_of_stock"}
            if record.attributes.get("disabled"):
                return {"error": "disabled_variant"}
            from factory_os.domain.order_hold import release_expired_unpaid_orders

            release_expired_unpaid_orders(store, identity.tenant_id)
            if record.variant_sku in store.held_variant_skus(identity.tenant_id):
                return {"error": "out_of_stock"}
        customer_id = payload["customer_id"]
        item = OrderItem(
            variant_sku=record.variant_sku,
            name=record.name,
            quantity=quantity,
            unit_price=record.price,
            currency=record.currency,
        )
        order = store.create_order(
            identity.tenant_id, customer_id, item, fulfill_on=fulfill_on
        )
        result = {
            "order_id": str(order.id),
            "name": record.name,
            "price": str(record.price),
            "currency": record.currency,
            "sku": record.product_sku,
            "quantity": quantity,
        }
        if fulfill_on is not None:
            result["fulfill_on"] = fulfill_on.isoformat()
            result["owner_notice"] = owner_notice(order)
        return result

    def payment_create_qr(identity: Identity, payload: dict[str, Any]) -> dict[str, Any]:
        from uuid import UUID

        from factory_os.domain.cart_quote import charge_total, quote_lines

        cart_raw = payload.get("cart") if isinstance(payload.get("cart"), list) else []
        hold_minutes = int(payload.get("hold_minutes") or 15)
        variant_sku = str(payload.get("variant_sku") or "")
        order_id_raw = payload.get("order_id")
        from factory_os.domain.future_orders import business_today, owner_notice, parse_fulfill_on

        try:
            fulfill_on = parse_fulfill_on(payload.get("fulfill_on"), today=business_today())
        except ValueError as exc:
            return {"error": str(exc)}
        if not cart_raw and not order_id_raw and variant_sku:
            cart_raw = [
                {"variant_sku": variant_sku, "quantity": int(payload.get("quantity") or 1)}
            ]
        customer_id: UUID | None = None
        if cart_raw:
            replace_raw = payload.get("replace_order_id")
            if replace_raw:
                _drop_unpaid_reservation(store, identity.tenant_id, UUID(str(replace_raw)))
            built = _items_from_cart(
                store, identity.tenant_id, cart_raw, check_stock=fulfill_on is None
            )
            if isinstance(built, dict):
                return built
            try:
                customer_id = UUID(str(payload.get("customer_id") or ""))
            except ValueError:
                return {"error": "unknown_customer"}
            quote = quote_lines(built)
            order = store.create_order(
                identity.tenant_id,
                customer_id,
                items=built,
                status="reserved",
                discount_amount=quote.discount,
                hold_minutes=hold_minutes,
                fulfill_on=fulfill_on,
            )
            variant_sku = variant_sku or built[0].variant_sku
            amount = quote.total
            currency = quote.currency
        else:
            if not order_id_raw:
                return {"error": "unknown_order"}
            order = store.get_order(identity.tenant_id, UUID(str(order_id_raw)))
            if order is None or not order.items:
                return {"error": "unknown_order"}
            quote = quote_lines(order.items)
            amount = charge_total(order.items, order.discount_amount)
            currency = order.items[0].currency
            variant_sku = variant_sku or order.items[0].variant_sku
            customer_id = order.customer_id
            hold_minutes = order.hold_minutes or hold_minutes
        issued = payments.create_qr(str(order.id), amount, currency)
        payment = store.create_payment(
            identity.tenant_id,
            order.id,
            payments.name,
            issued.provider_ref,
            amount,
            currency,
            issued.qr_payload,
            variant_sku=variant_sku,
            customer_id=customer_id,
        )
        result = {
            "payment_id": str(payment.id),
            "order_id": str(payment.order_id) if payment.order_id else None,
            "provider_ref": issued.provider_ref,
            "qr": issued.qr_payload,
            "amount": str(amount),
            "currency": currency,
            "discount": str(order.discount_amount),
            "subtotal": str(quote.subtotal),
            "hold_minutes": hold_minutes,
            "lines": quote.as_dict()["lines"],
            "status": payment.status.value,
            "expires_at": issued.expires_at.isoformat() if issued.expires_at else None,
        }
        if getattr(order, "fulfill_on", None) is not None:
            result["fulfill_on"] = order.fulfill_on.isoformat()
            result["owner_notice"] = owner_notice(order)
        return result

    def payment_status(identity: Identity, payload: dict[str, Any]) -> dict[str, Any]:
        ref = str(payload.get("provider_ref") or "")
        adapter_status = payments.status(ref)
        if adapter_status is PaymentStatus.CONFIRMED:
            store.confirm_from_adapter(ref)
        payment = store.payment_status(identity.tenant_id, ref)
        status = adapter_status.value if payment else PaymentStatus.UNKNOWN.value
        return {"provider_ref": ref, "status": status}

    def customer_update(identity: Identity, payload: dict[str, Any]) -> dict[str, Any]:
        customer = store.update_customer(
            identity.tenant_id,
            str(payload["wa_number"]),
            payload.get("name"),
            payload.get("address"),
        )
        return {"name": customer.name, "address": customer.address}

    def delivery_create(identity: Identity, payload: dict[str, Any]) -> dict[str, Any]:
        from uuid import UUID

        order_id = UUID(str(payload["order_id"]))
        order = store.get_order(identity.tenant_id, order_id)
        if order is None:
            return {"error": "unknown_order"}
        payment = store.payment_for_order(identity.tenant_id, order_id)
        if payment is None or payment.status is not PaymentStatus.CONFIRMED:
            return {"error": "payment_not_confirmed"}
        delivery = store.create_delivery(
            identity.tenant_id,
            order_id,
            str(payload.get("address") or ""),
            str(payload.get("recipient_name") or ""),
        )
        return {"delivery_id": str(delivery.id), "address": delivery.address}

    def inventory_adjust(identity: Identity, payload: dict[str, Any]) -> dict[str, Any]:
        record = store.adjust_stock(
            identity.tenant_id,
            str(payload["variant_sku"]),
            int(payload["delta"]),
        )
        return {
            "variant_sku": record.variant_sku,
            "stock": record.stock,
            "name": record.name,
        }

    def catalog_upsert(identity: Identity, payload: dict[str, Any]) -> dict[str, Any]:
        variant_sku = str(payload["variant_sku"])
        existing = store.get_variant(identity.tenant_id, variant_sku)
        name = str(payload.get("name") or (existing.name if existing else ""))
        product_sku = str(payload.get("product_sku") or (existing.product_sku if existing else variant_sku))
        description = str(payload.get("description") or (existing.description if existing else ""))
        category = str(payload.get("category") or (existing.category if existing else "general"))
        price = Decimal(str(payload.get("price") if payload.get("price") is not None else (existing.price if existing else "0")))
        currency = str(payload.get("currency") or (existing.currency if existing else "BOB"))
        stock = int(payload["stock"] if payload.get("stock") is not None else (existing.stock if existing else 0))
        attributes = dict(existing.attributes if existing else {})
        attributes.update(dict(payload.get("attributes") or {}))
        blob = " ".join([name, description, category, product_sku, variant_sku])
        record = VariantRecord(
            product_sku=product_sku,
            variant_sku=variant_sku,
            name=name,
            description=description,
            category=category,
            attributes=attributes,
            price=price,
            currency=currency,
            stock=stock,
            tokens=tokenize(blob),
        )
        stored = store.put_variant(identity.tenant_id, record)
        return {
            "variant_sku": stored.variant_sku,
            "product_sku": stored.product_sku,
            "name": stored.name,
            "price": str(stored.price),
            "stock": stored.stock,
        }

    def catalog_disable(identity: Identity, payload: dict[str, Any]) -> dict[str, Any]:
        record = store.disable_variant(identity.tenant_id, str(payload["variant_sku"]))
        return {"variant_sku": record.variant_sku, "disabled": True}

    def cash_record(identity: Identity, payload: dict[str, Any]) -> dict[str, Any]:
        # Staff tool path: auto-open float 0 when no session (HTTP panel still requires open).
        from factory_os.domain.cash_drawer import ensure_open_session

        currency = str(payload.get("currency") or "BOB")
        ensure_open_session(
            store, identity.tenant_id, currency=currency, opened_by_name="sistema"
        )
        movement = store.record_cash(
            identity.tenant_id,
            str(payload["direction"]),
            Decimal(str(payload["amount"])),
            currency,
            str(payload.get("reason") or ""),
        )
        return {
            "id": str(movement.id),
            "direction": movement.direction,
            "amount": str(movement.amount),
            "currency": movement.currency,
            "reason": movement.reason,
        }

    def cash_ledger(identity: Identity, payload: dict[str, Any]) -> dict[str, Any]:
        _ = payload
        from factory_os.domain.cash_drawer import sum_session_cash

        movements = store.list_cash(identity.tenant_id)
        incoming, outgoing = sum_session_cash(movements)
        return {
            "in": str(incoming),
            "out": str(outgoing),
            "balance": str(incoming - outgoing),
            "count": len(movements),
            "note": "Caja interna. Los QR de clientes los confirma Cobros, no este libro.",
        }

    def metrics_summary(identity: Identity, payload: dict[str, Any]) -> dict[str, Any]:
        from factory_os.domain.analytics import build_analytics_summary, parse_instant

        try:
            return build_analytics_summary(
                store,
                identity.tenant_id,
                period=str(payload.get("period") or "7d"),
                now=parse_instant(payload.get("now")),
                date_from=parse_instant(payload.get("date_from")),
                date_to=parse_instant(payload.get("date_to")),
            )
        except ValueError:
            return {"error": "bad_period"}

    def stock_receive(identity: Identity, payload: dict[str, Any]) -> dict[str, Any]:
        from uuid import UUID

        quantity = int(payload["quantity"])
        sku = str(payload["variant_sku"])
        raw_cost = payload.get("unit_cost")
        if raw_cost not in (None, ""):
            supplier_raw = payload.get("supplier_id")
            supplier_id = UUID(str(supplier_raw)) if supplier_raw not in (None, "") else None
            receipt = store.receive_purchase(
                identity.tenant_id,
                sku,
                quantity,
                Decimal(str(raw_cost)),
                str(payload.get("currency") or "BOB"),
                payment_method=str(payload.get("payment_method") or "cash"),
                supplier_id=supplier_id,
            )
            record = store.get_variant(identity.tenant_id, sku)
            return {
                "variant_sku": sku,
                "name": record.name if record else sku,
                "received": quantity,
                "stock": record.stock if record else 0,
                "purchase_id": str(receipt.id),
                "payment_method": receipt.payment_method,
                "supplier_id": str(receipt.supplier_id) if receipt.supplier_id else None,
            }
        record = store.adjust_stock(identity.tenant_id, sku, quantity)
        return {
            "variant_sku": record.variant_sku,
            "name": record.name,
            "received": quantity,
            "stock": record.stock,
        }

    def supplier_alert(identity: Identity, payload: dict[str, Any]) -> dict[str, Any]:
        _ = payload
        from factory_os.domain.suppliers import list_low_stock

        low = [
            {
                "variant_sku": record.variant_sku,
                "name": record.name,
                "stock": record.stock,
                "reorder_threshold": record.reorder_threshold,
            }
            for record in list_low_stock(store, limit=10)
        ]
        return {
            "low_stock": low,
            "contact_supplier": False,
            "note": "El contacto automático a proveedores todavía no está habilitado.",
        }

    def ledger_read(identity: Identity, payload: dict[str, Any]) -> dict[str, Any]:
        _ = payload
        from factory_os.domain.ledger import sync_facts

        sync_facts(store, identity.tenant_id)
        entries = store.list_ledger(identity.tenant_id)
        return {
            "entries": [
                {
                    "id": str(entry.id),
                    "source": entry.source,
                    "source_id": str(entry.source_id),
                    "direction": entry.direction,
                    "amount": str(entry.amount),
                    "currency": entry.currency,
                }
                for entry in entries
            ]
        }

    def invoice_issue(identity: Identity, payload: dict[str, Any]) -> dict[str, Any]:
        from uuid import UUID

        from factory_os.domain.invoicing import FakeInvoicePort, issue_invoice

        port = invoices if invoices is not None else FakeInvoicePort()
        document = issue_invoice(
            store,
            port,
            identity.tenant_id,
            UUID(str(payload["order_id"])),
        )
        return {
            "id": str(document.id),
            "order_id": str(document.order_id),
            "status": document.status,
            "external_ref": document.external_ref,
            "amount": str(document.amount),
            "currency": document.currency,
        }

    def notice_send(identity: Identity, payload: dict[str, Any]) -> dict[str, Any]:
        _ = identity
        return {
            "customer_id": str(payload.get("customer_id") or ""),
            "kind": str(payload.get("kind") or ""),
            "body": str(payload.get("body") or ""),
        }

    def send_product_image(identity: Identity, payload: dict[str, Any]) -> dict[str, Any]:
        """Send the catalog primary image; caption and bytes come from the store only."""
        from datetime import UTC, datetime
        from uuid import UUID, uuid4

        from factory_os.domain.media import (
            primary_product_media_link,
            product_image_caption,
            read_media_bytes,
        )
        from factory_os.domain.models import ConversationMedia

        product_sku = str(payload.get("product_sku") or "").strip()
        wa_number = str(payload.get("wa_number") or "").strip()
        caption = product_image_caption(store, identity.tenant_id, product_sku)
        link = primary_product_media_link(store, identity.tenant_id, product_sku)
        if link is None:
            return {
                "ok": False,
                "error": "no_image",
                "product_sku": product_sku,
                "caption": caption,
                "message": "No hay foto de catálogo para ese producto.",
            }
        asset = store.get_media_asset(identity.tenant_id, link.asset_id)
        if asset is None:
            return {
                "ok": False,
                "error": "no_image",
                "product_sku": product_sku,
                "caption": caption,
                "message": "No hay foto de catálogo para ese producto.",
            }
        try:
            content = read_media_bytes(asset.storage_key)
        except FileNotFoundError:
            return {
                "ok": False,
                "error": "no_image",
                "product_sku": product_sku,
                "caption": caption,
                "message": "No hay foto de catálogo para ese producto.",
            }
        if channel is None or not wa_number:
            return {"ok": False, "error": "no_channel", "product_sku": product_sku}
        filename = f"{product_sku}.{(asset.mime or 'image/png').split('/')[-1]}"
        channel.send_image(
            wa_number,
            content=content,
            mime=asset.mime or "image/png",
            filename=filename,
            caption=caption,
        )
        conversation_id_raw = payload.get("conversation_id")
        try:
            conversation_id = UUID(str(conversation_id_raw or ""))
        except ValueError:
            conversation_id = None
        if conversation_id is not None:
            store.add_conversation_media(
                identity.tenant_id,
                ConversationMedia(
                    id=uuid4(),
                    tenant_id=identity.tenant_id,
                    conversation_id=conversation_id,
                    asset_id=asset.id,
                    direction="outbound",
                    status="ready",
                    kind="image",
                    mime=asset.mime,
                    filename=filename,
                    size_bytes=asset.size_bytes,
                    uploaded_by=identity.employee_name,
                    created_at=datetime.now(UTC),
                ),
            )
        return {
            "ok": True,
            "sent": True,
            "product_sku": product_sku,
            "asset_id": str(asset.id),
            "caption": caption,
            "size": len(content),
        }

    return ToolRuntime(
        [
            ToolSpec("catalog.search", "catalog.search", True, catalog_search, description="Structured catalog read"),
            ToolSpec("cart.add", "cart.add", False, cart_add, description="Add a real variant to the cart"),
            ToolSpec("cart.remove", "cart.remove", False, cart_remove, description="Remove a variant from the cart"),
            ToolSpec(
                "order.create",
                "order.create",
                False,
                order_create,
                confirmation_required=True,
                description="Create an order from a catalog variant. fulfill_on (YYYY-MM-DD) schedules it for another day and does not take today's stock.",
            ),
            ToolSpec("payment.create_qr", "payment.create_qr", False, payment_create_qr, description="Issue payment QR. fulfill_on schedules a later day without taking today's stock."),
            ToolSpec("payment.status", "payment.status", True, payment_status, description="Adapter payment status"),
            ToolSpec("customer.update_profile", "customer.update_profile", False, customer_update, description="Save shipping profile"),
            ToolSpec("delivery.create", "delivery.create", False, delivery_create, description="Register delivery"),
            ToolSpec(
                "inventory.adjust",
                "inventory.adjust",
                False,
                inventory_adjust,
                confirmation_required=True,
                description="Adjust stock quantity",
            ),
            ToolSpec(
                "catalog.upsert",
                "catalog.upsert",
                False,
                catalog_upsert,
                confirmation_required=True,
                description="Create or update a catalog variant",
            ),
            ToolSpec(
                "catalog.disable",
                "catalog.disable",
                False,
                catalog_disable,
                confirmation_required=True,
                description="Disable a catalog variant",
            ),
            ToolSpec(
                "cash.record",
                "cash.record",
                False,
                cash_record,
                confirmation_required=True,
                description="Record a cash-drawer movement; not a customer QR",
            ),
            ToolSpec("cash.ledger", "cash.ledger", True, cash_ledger, description="Read cash-drawer totals"),
            ToolSpec("metrics.summary", "metrics.summary", True, metrics_summary, description="Read business metrics"),
            ToolSpec(
                "stock.receive",
                "stock.receive",
                False,
                stock_receive,
                confirmation_required=True,
                description="Receive supplier stock into inventory",
            ),
            ToolSpec(
                "supplier.alert",
                "supplier.alert",
                True,
                supplier_alert,
                description="List low stock; does not message a supplier yet",
            ),
            ToolSpec("ledger.read", "ledger.read", True, ledger_read, description="Read the operating ledger"),
            ToolSpec(
                "invoice.issue",
                "invoice.issue",
                False,
                invoice_issue,
                description="Submit an invoice document. Does not confirm a payment.",
            ),
            ToolSpec(
                "notice.send",
                "notice.send",
                False,
                notice_send,
                description="Authorize a fixed customer notice. Does not sell or confirm a payment.",
            ),
            ToolSpec(
                "send_product_image",
                "send_product_image",
                True,
                send_product_image,
                description="Send the catalog primary image for a product_sku. Caption from store only.",
            ),
        ],
        policy=PolicyEngine(store),
    )
