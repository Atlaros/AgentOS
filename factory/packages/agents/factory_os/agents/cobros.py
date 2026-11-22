from __future__ import annotations

from uuid import UUID

from factory_os.contracts.employees import Identity
from factory_os.domain.models import Conversation, ConversationStage, EmployeeRole, NextAction, PaymentStatus
from factory_os.harness.context import compile_context
from factory_os.harness.model_gateway import ActionProposal, FakeGateway, ModelGateway, render_reply
from factory_os.harness.tools import ToolRuntime, run_tool
from factory_os.tools.qr_media import looks_like_image_payload

# Exact strings from channel button ids + receipt media → Cobros READ status (not confirm).
_BUTTON_PAID = frozenset({"ya pagué", "ya pague"})
_BUTTON_RESEND = frozenset({"reenviame el qr"})
_RECEIPT_MARKERS = (
    "comprobante",
    "te envío el comprobante",
    "te envio el comprobante",
    "aqui el comprobante",
    "aquí el comprobante",
    "mande el comprobante",
    "mandé el comprobante",
    "envio el comprobante",
    "envío el comprobante",
    "transferencia",
    "captura del pago",
    "screenshot del pago",
)


def _item_noun(store, tenant_id) -> str:
    """Customer item word from the shop card. Missing card stays 'prenda'."""
    from factory_os.domain.knowledge import item_word, pack_for_tenant

    return item_word(pack_for_tenant(store, tenant_id))


def handle_cobros(
    identity: Identity,
    runtime: ToolRuntime,
    conversation: Conversation,
    gateway: ModelGateway | None = None,
    text: str = "",
    store=None,
) -> str:
    desk = gateway or FakeGateway()
    if conversation.state.provider_ref is None:
        has_cart = bool(conversation.state.cart)
        if (
            conversation.state.order_id is None
            and not conversation.state.considered_variant_sku
            and not has_cart
        ):
            conversation.state.pass_to(
                EmployeeRole.SALES,
                from_role=EmployeeRole.COBROS,
                reason="no_order",
                payment_state="none",
            )
            conversation.state.last_skill = "payment_initiation"
            noun = _item_noun(store, conversation.tenant_id)
            return _say(
                desk,
                identity,
                conversation,
                f"Todavía no hay {noun} elegida. Te devuelvo con Adri para elegir.",
                {"payment_status": "none"},
            )
        return _issue_qr(desk, identity, runtime, conversation, store=store)

    conversation.state.last_skill = "payment_verification"
    status = run_tool(
        runtime,
        identity,
        conversation,
        "payment.status",
        {"provider_ref": conversation.state.provider_ref},
    )
    if status.get("status") == PaymentStatus.CONFIRMED.value:
        if store is not None and conversation.state.order_id is None and conversation.state.provider_ref:
            payment = store.payment_status(conversation.tenant_id, conversation.state.provider_ref)
            if payment is not None and payment.order_id is not None:
                conversation.state.order_id = payment.order_id
        conversation.state.pass_to(
            EmployeeRole.OPS,
            from_role=EmployeeRole.COBROS,
            pending="collect_address",
            reason="payment_confirmed",
            payment_state="confirmed",
        )
        conversation.state.stage = ConversationStage.PURCHASED
        return _say(
            desk,
            identity,
            conversation,
            "El pago llegó. Pago confirmado por el banco. Te paso con Operaciones para el envío. "
            "Cuando puedas, compartí tu ubicación de Maps o escribí la dirección.",
            {"payment_status": "confirmed"},
        )

    proposed = desk.propose(
        role=identity.role.value,
        context=compile_context(identity, conversation),
        text=text,
        state=conversation.state,
    )
    if _wants_resend(text, proposed):
        return _resend_qr(desk, identity, runtime, conversation, store=store)

    # Pending: never confirm from customer text/image. Button, receipt, or free chat → wait path.
    claimed = _is_payment_claim(text)
    conversation.state.pass_to(
        EmployeeRole.COBROS,
        from_role=EmployeeRole.COBROS,
        pending="wait_adapter",
        reason="customer_claimed_paid" if claimed else "qr_awaiting_bank",
        payment_state="pending",
    )
    if claimed:
        via = "el comprobante" if _is_receipt_claim(text) else "el botón o decir que ya pagaste"
        msg = (
            f"Recibí {via}: consulto al banco ahora. "
            "El pago sigue pendiente en el sistema — solo el banco confirma el cobro. "
            "Cuando confirme el QR, avanzamos con el envío. Si no ves el QR, tocá Reenviar QR."
        )
    else:
        msg = (
            "El QR ya está listo: pagá con la imagen, mandame el comprobante o tocá Ya transferí "
            "para consultar al banco (eso no confirma el cobro). Si no ves la imagen, tocá Reenviar QR."
        )
    return _say(desk, identity, conversation, msg, {"payment_status": "pending"})


def _is_button_paid(text: str) -> bool:
    return (text or "").strip().lower() in _BUTTON_PAID


def _is_receipt_claim(text: str) -> bool:
    blob = (text or "").strip().lower()
    return any(marker in blob for marker in _RECEIPT_MARKERS)


def _is_payment_claim(text: str) -> bool:
    """Button 'Ya transferí' or receipt media/caption — READ status only, never WRITE paid."""
    return _is_button_paid(text) or _is_receipt_claim(text)

def _wants_resend(text: str, proposed: ActionProposal | None) -> bool:
    if (text or "").strip().lower() in _BUTTON_RESEND:
        return True
    if proposed is None:
        return False
    op = str((proposed.arguments or {}).get("op") or "").strip().lower()
    if op in {"resend_qr", "qr_resent", "resend"}:
        return True
    if proposed.action is NextAction.HANDOFF and op == "resend_qr":
        return True
    return False


def _qr_text(
    conversation: Conversation,
    store,
    *,
    qr: str,
    lines: list | None,
    hold_minutes: int,
    resent: bool = False,
) -> str:
    from factory_os.domain.cart_quote import format_checkout_copy, quote_lines
    from factory_os.tools.qr_media import looks_like_image_payload

    source = lines
    minutes = hold_minutes
    if not source and store is not None and conversation.state.order_id is not None:
        order = store.get_order(conversation.tenant_id, conversation.state.order_id)
        if order is not None and order.items:
            source = order.items
            minutes = order.hold_minutes or minutes
    if not source:
        head = "Acá va de nuevo el QR para pagar" if resent else "Para pagar con QR"
        if looks_like_image_payload(qr):
            return f"{head}. Te mando la imagen del código. Cuando el banco confirme, seguimos con el envío."
        return f"{head}: {qr}. Cuando el banco confirme, seguimos con el envío."
    return format_checkout_copy(
        quote_lines(source),
        hold_minutes=minutes,
        qr=qr,
        image=looks_like_image_payload(qr),
        resent=resent,
        item_noun=_item_noun(store, conversation.tenant_id),
    )


def _issue_qr(
    desk: ModelGateway,
    identity: Identity,
    runtime: ToolRuntime,
    conversation: Conversation,
    store=None,
) -> str:
    from factory_os.domain.cart_quote import hold_minutes_for

    conversation.state.last_skill = "payment_initiation"
    payload: dict[str, object] = {
        "customer_id": str(conversation.customer_id),
        "hold_minutes": hold_minutes_for(conversation.live_code),
    }
    if conversation.state.fulfill_on:
        payload["fulfill_on"] = conversation.state.fulfill_on
    cart = [
        item
        for item in conversation.state.cart
        if isinstance(item, dict) and item.get("variant_sku")
    ]
    if cart:
        payload["cart"] = [
            {"variant_sku": item.get("variant_sku"), "quantity": item.get("quantity") or 1}
            for item in cart
        ]
        payload["variant_sku"] = conversation.state.considered_variant_sku or cart[0].get("variant_sku")
        if conversation.state.order_id is not None:
            payload["replace_order_id"] = str(conversation.state.order_id)
    elif conversation.state.order_id is not None:
        payload["order_id"] = str(conversation.state.order_id)
        if conversation.state.considered_variant_sku:
            payload["variant_sku"] = conversation.state.considered_variant_sku
    elif conversation.state.considered_variant_sku:
        payload["variant_sku"] = conversation.state.considered_variant_sku
    created = run_tool(
        runtime,
        identity,
        conversation,
        "payment.create_qr",
        payload,
    )
    if created.get("error"):
        return _say(
            desk,
            identity,
            conversation,
            (
                f"No pude emitir el QR de esa {_item_noun(store, conversation.tenant_id)}. "
                "¿Seguimos con Adri y elegimos otra?"
            ),
            {"payment_status": "none"},
        )
    conversation.state.payment_id = UUID(created["payment_id"])
    conversation.state.provider_ref = created["provider_ref"]
    if created.get("order_id"):
        conversation.state.order_id = UUID(str(created["order_id"]))
    conversation.state.pass_to(
        EmployeeRole.COBROS,
        from_role=EmployeeRole.COBROS,
        pending="wait_adapter",
        reason="qr_issued",
        payment_state="pending",
    )
    qr = str(created.get("qr") or "")
    amount = created.get("amount")
    currency = created.get("currency") or "BOB"
    return _say(
        desk,
        identity,
        conversation,
        _qr_text(
            conversation,
            store,
            qr=qr,
            lines=created.get("lines") or None,
            hold_minutes=int(created.get("hold_minutes") or payload["hold_minutes"]),
        ),
        {
            "payment_status": "pending",
            "price": amount,
            "currency": currency,
            "qr": qr if not looks_like_image_payload(qr) else "",
        },
    )


def _resend_qr(
    desk: ModelGateway,
    identity: Identity,
    runtime: ToolRuntime,
    conversation: Conversation,
    *,
    store=None,
) -> str:
    """Explicit resend (button or model proposal) — re-read payload, don't lecture."""
    _ = runtime
    conversation.state.last_skill = "payment_initiation"
    qr = ""
    amount = ""
    currency = "BOB"
    payment = None
    if store is not None and conversation.state.payment_id is not None:
        payment = store.get_payment(conversation.tenant_id, conversation.state.payment_id)
    if payment is not None:
        qr = str(payment.qr_payload or payment.provider_ref or "")
        amount = str(payment.amount)
        currency = payment.currency or "BOB"
    if not qr and conversation.state.provider_ref:
        qr = str(conversation.state.provider_ref)
    if not qr or not looks_like_image_payload(qr):
        # A fake "QR:pay-…" ref cannot be shown. With Baneco live, mint a real image.
        from factory_os.tools.payments import build_payment_provider, live_payments_enabled

        if not qr or (live_payments_enabled() and build_payment_provider().name == "baneco"):
            return _issue_qr(desk, identity, runtime, conversation, store=store)
    conversation.state.pass_to(
        EmployeeRole.COBROS,
        from_role=EmployeeRole.COBROS,
        pending="wait_adapter",
        reason="qr_resent",
        payment_state="pending",
    )
    return _say(
        desk,
        identity,
        conversation,
        _qr_text(
            conversation,
            store,
            qr=qr,
            lines=None,
            hold_minutes=15,
            resent=True,
        ),
        {
            "payment_status": "pending",
            "price": amount,
            "currency": currency,
            "qr": qr if not looks_like_image_payload(qr) else "",
        },
    )


def _say(
    gateway: ModelGateway,
    identity: Identity,
    conversation: Conversation,
    fallback: str,
    extra: dict | None = None,
) -> str:
    facts = {"hits": list(conversation.state.last_hits)}
    if extra:
        facts.update(extra)
    reply = render_reply(
        gateway,
        role=identity.role.value,
        context=compile_context(identity, conversation),
        fallback=fallback,
        facts=facts,
    )
    qr = str((extra or {}).get("qr") or "").strip()
    if qr and not looks_like_image_payload(qr) and qr not in reply:
        reply = f"{reply.rstrip()}\n\nPara pagar: {qr}"
    return reply
