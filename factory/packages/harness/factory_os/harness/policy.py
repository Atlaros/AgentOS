from __future__ import annotations

from typing import Any
from uuid import UUID

from factory_os.contracts.employees import Identity
from factory_os.domain.models import PaymentStatus
from factory_os.domain.reports import NOTICE_BODIES, SEND_ROLE
from factory_os.domain.store import CommerceStore


class PolicyDenied(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class PolicyEngine:
    """Decision rules before a tool runs. The handler still validates."""

    def __init__(self, store: CommerceStore) -> None:
        self.store = store

    def evaluate(self, identity: Identity, tool_name: str, payload: dict[str, Any]) -> None:
        tenant_id = identity.tenant_id
        from factory_os.domain.future_orders import business_today, parse_fulfill_on

        try:
            scheduled = parse_fulfill_on(payload.get("fulfill_on"), today=business_today())
        except ValueError:
            scheduled = None
        if tool_name in {"cart.add", "order.create", "inventory.adjust", "catalog.disable"}:
            sku = str(payload.get("variant_sku") or "")
            if not sku:
                raise PolicyDenied("missing_variant", "variant_sku is required")
            if self.store.get_variant(tenant_id, sku) is None:
                raise PolicyDenied("unknown_variant", "variant is not in the structured catalog")
        if tool_name == "cart.add":
            from factory_os.domain.stock import tracks_stock

            quantity = int(payload.get("quantity") or 1)
            if quantity < 1:
                raise PolicyDenied("bad_quantity", "quantity must be at least 1")
            record = self.store.get_variant(tenant_id, str(payload["variant_sku"]))
            if (
                record is not None
                and tracks_stock(record)
                and record.stock < quantity
            ):
                raise PolicyDenied("out_of_stock", "not enough stock")
        if tool_name == "order.create" and scheduled is None:
            from factory_os.domain.stock import tracks_stock

            record = self.store.get_variant(tenant_id, str(payload.get("variant_sku") or ""))
            if record is not None and tracks_stock(record) and record.stock < 1:
                raise PolicyDenied("out_of_stock", "not enough stock")
            if record is not None and record.attributes.get("disabled"):
                raise PolicyDenied("disabled_variant", "variant is disabled")
        if tool_name == "payment.create_qr":
            variant_sku = str(payload.get("variant_sku") or "")
            order_raw = str(payload.get("order_id") or "")
            cart_raw = payload.get("cart") if isinstance(payload.get("cart"), list) else []
            replace_raw = str(payload.get("replace_order_id") or "")
            held = self.store.held_variant_skus(tenant_id)
            if replace_raw:
                try:
                    previous = self.store.get_order(tenant_id, UUID(replace_raw))
                except ValueError:
                    previous = None
                if previous is not None:
                    held -= {item.variant_sku for item in previous.items}
            if cart_raw:
                from factory_os.domain.stock import tracks_stock

                for raw in cart_raw:
                    if not isinstance(raw, dict):
                        continue
                    sku = str(raw.get("variant_sku") or "")
                    record = self.store.get_variant(tenant_id, sku)
                    if record is None:
                        raise PolicyDenied("unknown_variant", "variant is not in the catalog")
                    qty = int(raw.get("quantity") or 1)
                    if scheduled is None and record.attributes.get("disabled"):
                        raise PolicyDenied("out_of_stock", "variant is not for sale")
                    if (
                        scheduled is None
                        and tracks_stock(record)
                        and record.stock < qty
                    ):
                        raise PolicyDenied("out_of_stock", "variant is not for sale")
                    if scheduled is None and tracks_stock(record) and record.variant_sku in held:
                        raise PolicyDenied("out_of_stock", "variant is held")
            elif order_raw:
                try:
                    order_id = UUID(order_raw)
                except ValueError as exc:
                    raise PolicyDenied("unknown_order", "order_id is required") from exc
                if self.store.get_order(tenant_id, order_id) is None:
                    raise PolicyDenied("unknown_order", "order is not in the store")
            elif variant_sku:
                from factory_os.domain.stock import tracks_stock

                record = self.store.get_variant(tenant_id, variant_sku)
                if record is None:
                    raise PolicyDenied("unknown_variant", "variant is not in the catalog")
                if scheduled is None and record.attributes.get("disabled"):
                    raise PolicyDenied("out_of_stock", "variant is not for sale")
                if scheduled is None and tracks_stock(record) and record.stock < 1:
                    raise PolicyDenied("out_of_stock", "variant is not for sale")
                if scheduled is None and tracks_stock(record) and record.variant_sku in held:
                    raise PolicyDenied("out_of_stock", "variant is held")
            else:
                raise PolicyDenied("unknown_order", "variant_sku or order_id is required")
        if tool_name == "delivery.create":
            try:
                order_id = UUID(str(payload.get("order_id") or ""))
            except ValueError as exc:
                raise PolicyDenied("unknown_order", "order_id is required") from exc
            order = self.store.get_order(tenant_id, order_id)
            if order is None:
                raise PolicyDenied("unknown_order", "order is not in the store")
            payment = self.store.payment_for_order(tenant_id, order_id)
            if payment is None or payment.status is not PaymentStatus.CONFIRMED:
                raise PolicyDenied("payment_not_confirmed", "delivery requires confirmed payment")
            if not str(payload.get("address") or "").strip() or not str(payload.get("recipient_name") or "").strip():
                raise PolicyDenied("missing_shipping", "name and address are required")
        if tool_name == "catalog.upsert":
            if not str(payload.get("variant_sku") or "").strip():
                raise PolicyDenied("missing_variant", "variant_sku is required")
            if not str(payload.get("name") or "").strip() and self.store.get_variant(tenant_id, str(payload["variant_sku"])) is None:
                raise PolicyDenied("missing_name", "name is required for a new variant")
        if tool_name == "inventory.adjust":
            try:
                delta = int(payload.get("delta"))
            except (TypeError, ValueError) as exc:
                raise PolicyDenied("bad_delta", "delta must be an integer") from exc
            record = self.store.get_variant(tenant_id, str(payload.get("variant_sku") or ""))
            if record is not None and record.stock + delta < 0:
                raise PolicyDenied("negative_stock", "stock cannot go below zero")
        if tool_name == "stock.receive":
            sku = str(payload.get("variant_sku") or "")
            if not sku:
                raise PolicyDenied("missing_variant", "variant_sku is required")
            if self.store.get_variant(tenant_id, sku) is None:
                raise PolicyDenied("unknown_variant", "variant is not in the structured catalog")
            try:
                quantity = int(payload.get("quantity"))
            except (TypeError, ValueError) as exc:
                raise PolicyDenied("bad_quantity", "quantity must be a positive integer") from exc
            if quantity < 1:
                raise PolicyDenied("bad_quantity", "receive quantity must be at least 1")
        if tool_name == "cash.record":
            direction = str(payload.get("direction") or "")
            if direction not in {"in", "out"}:
                raise PolicyDenied("bad_direction", "direction must be in or out")
            try:
                amount = float(payload.get("amount"))
            except (TypeError, ValueError) as exc:
                raise PolicyDenied("bad_amount", "amount must be a number") from exc
            if amount <= 0:
                raise PolicyDenied("bad_amount", "amount must be greater than zero")
        if tool_name == "notice.send":
            kind = str(payload.get("kind") or "")
            body = str(payload.get("body") or "")
            if kind not in NOTICE_BODIES or body != NOTICE_BODIES[kind]:
                raise PolicyDenied("notice_script", "a reminder is a fixed notice, not a sales script")
            if identity.role is not SEND_ROLE[kind]:
                raise PolicyDenied("notice_role", "this employee does not send that notice")
            try:
                customer_id = UUID(str(payload.get("customer_id") or ""))
            except ValueError as exc:
                raise PolicyDenied("bad_customer", "customer_id is required") from exc
            if self.store.get_customer(tenant_id, customer_id) is None:
                raise PolicyDenied("unknown_customer", "customer is not in this tenant")
        if tool_name == "invoice.issue":
            if payload.get("mark_paid") or payload.get("confirm_payment"):
                raise PolicyDenied(
                    "invoice_does_not_confirm_payment",
                    "an issued invoice does not confirm a payment",
                )
            try:
                order_id = UUID(str(payload.get("order_id") or ""))
            except ValueError as exc:
                raise PolicyDenied("missing_order", "order_id is required") from exc
            if self.store.get_order(tenant_id, order_id) is None:
                raise PolicyDenied("unknown_order", "order is not in this tenant")
        if tool_name == "send_product_image":
            forbidden = {
                "url",
                "link",
                "path",
                "image_url",
                "caption",
                "image_path",
                "media_url",
                "href",
                "src",
                "filename",
                "content",
                "bytes",
            }
            for key in payload:
                if str(key).strip().lower() in forbidden:
                    raise PolicyDenied(
                        "model_media_url",
                        "send_product_image rejects url/path/caption from the model",
                    )
            if payload.get("human_takeover"):
                raise PolicyDenied("human_takeover", "agent must not send while Manual")
            product_sku = str(payload.get("product_sku") or "").strip()
            if not product_sku:
                raise PolicyDenied("unknown_product", "product_sku is required")
            variants = [
                record
                for record in self.store.iter_variants()
                if record.product_sku == product_sku
            ]
            if not variants:
                raise PolicyDenied("unknown_product", "product is not in the catalog")
            from factory_os.domain.stock import tracks_stock

            allow_oos = any(
                bool((record.attributes or {}).get("allow_send_out_of_stock"))
                for record in variants
            )
            sellable = False
            for record in variants:
                if (record.attributes or {}).get("disabled"):
                    continue
                if not tracks_stock(record):
                    sellable = True
                    break
                if int(record.stock or 0) >= 1:
                    sellable = True
                    break
            if not sellable and not allow_oos:
                raise PolicyDenied("out_of_stock", "product has no in-stock variants")
            sent = [
                str(item).strip()
                for item in (payload.get("sent_product_skus") or [])
                if str(item).strip()
            ]
            if product_sku in sent:
                raise PolicyDenied("already_sent", "same product already sent this turn")
            if len(sent) >= 3:
                raise PolicyDenied("turn_limit", "max product images per turn is 3")
