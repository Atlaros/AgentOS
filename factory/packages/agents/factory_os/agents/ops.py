from __future__ import annotations

import re
from typing import Any

from factory_os.contracts.employees import Identity
from factory_os.domain.models import Conversation, EmployeeRole
from factory_os.domain.seed import normalize
from factory_os.harness.context import compile_context
from factory_os.harness.model_gateway import ActionProposal, FakeGateway, ModelGateway, render_reply
from factory_os.harness.policy import PolicyDenied
from factory_os.harness.tools import ToolRuntime, run_tool

# Structured Maps pin from channel.parse_inbound — not a free-chat keyword list.
_MAPS_PIN = re.compile(
    r"ubicacion maps:\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)(?:\s*\(([^)]*)\))?",
    re.I,
)
_FAREWELL = frozenset(
    {
        "gracias",
        "gracia",
        "grasias",
        "chau",
        "chao",
        "adios",
        "adiós",
        "listo",
        "ok",
        "oka",
        "dale",
        "perfecto",
        "genial",
        "thanks",
        "bye",
    }
)


def _shop_pack(store, tenant_id):
    """Card for the thanks line. Missing card keeps the Closet display name."""
    from factory_os.domain.knowledge import pack_for_tenant

    return pack_for_tenant(store, tenant_id)


def handle_ops(
    identity: Identity,
    runtime: ToolRuntime,
    conversation: Conversation,
    wa_number: str,
    text: str,
    gateway: ModelGateway | None = None,
    store=None,
) -> str:
    desk = gateway or FakeGateway()
    if conversation.state.order_id is None:
        conversation.state.pass_to(
            EmployeeRole.SALES,
            from_role=EmployeeRole.OPS,
            reason="no_order",
            payment_state="none",
        )
        return _say(
            desk,
            identity,
            conversation,
            "No hay pedido todavía. Te paso con Adri.",
            {"payment_status": "none"},
        )

    proposed = desk.propose(
        role=identity.role.value,
        context=compile_context(identity, conversation),
        text=text,
        state=conversation.state,
    )
    name, address = _shipping_from_proposal(proposed, text)

    conversation.state.last_skill = "customer_delivery_data"
    profile = run_tool(
        runtime,
        identity,
        conversation,
        "customer.update_profile",
        {"wa_number": wa_number, "name": name, "address": address},
    )
    name = name or (str(profile.get("name") or "").strip() or None)
    address = address or (str(profile.get("address") or "").strip() or None)

    # WRITE when both shipping facts exist; proposal only supplies/extracts fields.
    # Runtime policy still blocks delivery without confirmed payment.
    want_create = bool(name and address)

    if not want_create:
        conversation.state.pass_to(
            EmployeeRole.OPS,
            from_role=EmployeeRole.OPS,
            pending="collect_address",
            reason="need_shipping_data",
            payment_state="confirmed",
        )
        farewell = _is_farewell(text)
        if address and not name:
            msg = (
                "Perfecto, ya tengo tu ubicación. "
                "¿Me decís tu nombre para registrar el envío? (por ejemplo: me llamo Ana)"
            )
            if farewell:
                msg = (
                    "¡Gracias! Ya tengo tu ubicación. "
                    "Solo me falta tu nombre para cerrar el envío (por ejemplo: me llamo Ana)."
                )
        elif name and not address:
            msg = (
                f"Gracias, {name}. Ahora compartí tu ubicación de Maps (clip → ubicación) "
                "o escribí la dirección."
            )
        elif farewell and (address or name):
            missing = "nombre" if not name else "ubicación"
            msg = f"¡Gracias! Para cerrar el envío solo me falta tu {missing}."
        else:
            msg = (
                "Pago ok. Para el envío necesito tu nombre y tu ubicación de Maps "
                "(o la dirección escrita)."
            )
        return _say(desk, identity, conversation, msg, {"payment_status": "confirmed"})

    conversation.state.last_skill = "delivery_management"
    try:
        created = run_tool(
            runtime,
            identity,
            conversation,
            "delivery.create",
            {
                "order_id": str(conversation.state.order_id),
                "recipient_name": name,
                "address": address,
            },
        )
    except PolicyDenied:
        conversation.state.pass_to(
            EmployeeRole.COBROS,
            from_role=EmployeeRole.OPS,
            pending="wait_adapter",
            reason="payment_not_confirmed",
            payment_state="pending",
        )
        return _say(
            desk,
            identity,
            conversation,
            "Todavía no puedo registrar el envío: el pago no está confirmado.",
            {"payment_status": "pending"},
        )
    if created.get("error"):
        conversation.state.pass_to(
            EmployeeRole.COBROS,
            from_role=EmployeeRole.OPS,
            pending="wait_adapter",
            reason="payment_not_confirmed",
            payment_state="pending",
        )
        return _say(
            desk,
            identity,
            conversation,
            "Todavía no puedo registrar el envío: el pago no está confirmado.",
            {"payment_status": "pending"},
        )
    conversation.state.pass_to(
        EmployeeRole.OPS,
        from_role=EmployeeRole.OPS,
        reason="delivery_registered",
        payment_state="confirmed",
        pending=None,
    )
    order_ref = "pedido"
    if store is not None and conversation.state.order_id is not None:
        order = store.get_order(conversation.tenant_id, conversation.state.order_id)
        if order is not None and order.public_number:
            order_ref = order.public_number
    from factory_os.domain.learning import mark_conversation_outcome

    mark_conversation_outcome(conversation, "success", reason="delivery_registered")
    window = ""
    if proposed is not None:
        window = str((proposed.arguments or {}).get("delivery_window") or "").strip()
    if store is not None and window:
        prefs = store.get_customer_preferences(conversation.tenant_id, conversation.customer_id)
        prefs["delivery_window"] = window
        store.put_customer_preferences(conversation.tenant_id, conversation.customer_id, prefs)
    extra = f" Horario anotado: {window}." if window else ""
    from factory_os.domain.knowledge import spoken_shop_name

    shop = spoken_shop_name(_shop_pack(store, conversation.tenant_id))
    return _say(
        desk,
        identity,
        conversation,
        (
            f"Listo, {name}. Envío registrado a {address}. "
            f"Tu número de pedido es #{order_ref} — guardalo para el seguimiento. "
            f"¡Gracias por comprar en {shop}! Cualquier duda, escribime.{extra}"
        ),
        {
            "payment_status": "confirmed",
            "delivery_ok": True,
            "name": name,
            "address": address,
            "order_ref": order_ref,
        },
    )


def _is_farewell(text: str) -> bool:
    tokens = set(normalize(text or "").split())
    return bool(tokens) and tokens <= _FAREWELL | {"por", "favor", "muchas", "mil"}


def _shipping_from_proposal(
    proposed: ActionProposal | None, text: str
) -> tuple[str | None, str | None]:
    name: str | None = None
    address: str | None = None
    if proposed is not None:
        args = proposed.arguments or {}
        name = str(args.get("name") or args.get("recipient_name") or "").strip() or None
        address = str(args.get("address") or "").strip() or None
    # Channel-structured Maps pin (parse_inbound), not free-chat keyword lists.
    if not address:
        address = _maps_pin_address(text)
    return name, address


def _maps_pin_address(text: str) -> str | None:
    maps = _MAPS_PIN.search(text or "")
    if not maps:
        return None
    lat, lon = maps.group(1), maps.group(2)
    label = (maps.group(3) or "").strip()
    if label and label.lower() not in {"ubicacion", "ubicación"}:
        return f"{label} (Maps {lat},{lon})"
    return f"Maps {lat},{lon}"


def _say(
    gateway: ModelGateway,
    identity: Identity,
    conversation: Conversation,
    fallback: str,
    extra: dict[str, Any] | None = None,
) -> str:
    facts: dict[str, Any] = {"hits": list(conversation.state.last_hits)}
    if extra:
        facts.update(extra)
    return render_reply(
        gateway,
        role=identity.role.value,
        context=compile_context(identity, conversation),
        fallback=fallback,
        facts=facts,
    )
