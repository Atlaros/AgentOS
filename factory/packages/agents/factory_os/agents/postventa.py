from __future__ import annotations

from factory_os.contracts.employees import Identity
from factory_os.domain.models import Conversation, ConversationStage, EmployeeRole
from factory_os.domain.seed import normalize
from factory_os.harness.context import compile_context
from factory_os.harness.model_gateway import FakeGateway, ModelGateway, render_reply
from factory_os.harness.tools import ToolRuntime, run_tool

_REPEAT = ("otro", "igual", "mismo", "repetir", "otra vez")
_INCIDENT = ("roto", "rotas", "danado", "danada", "reclamo", "devolucion", "garantia", "incidencia")


def _shop_pack(store, tenant_id):
    """Card for post-sale fallbacks. The graph call has no store argument."""
    from factory_os.domain.knowledge import pack_for_tenant

    if store is not None:
        return pack_for_tenant(store, tenant_id)
    try:
        from factory_os.agents.graph import _INVOKE_CTX
    except ImportError:
        return None
    bag_store = _INVOKE_CTX.get("store") if isinstance(_INVOKE_CTX, dict) else None
    return pack_for_tenant(bag_store, tenant_id)


def handle_postventa(
    identity: Identity,
    runtime: ToolRuntime,
    conversation: Conversation,
    text: str,
    gateway: ModelGateway | None = None,
    store=None,
) -> str:
    desk = gateway or FakeGateway()
    from factory_os.domain.knowledge import item_word, shop_label

    pack = _shop_pack(store, conversation.tenant_id)
    noun = item_word(pack)
    label = shop_label(pack)
    lowered = normalize(text)
    conversation.state.stage = ConversationStage.POST_SALE
    wants_sale = any(word in lowered for word in _REPEAT)
    is_incident = any(word in lowered for word in _INCIDENT) or "llego" in lowered

    if is_incident:
        conversation.state.last_skill = "incident_handling"
        conversation.state.incident = text
        if wants_sale:
            conversation.state.last_skill = "sales_handoff"
            conversation.state.pass_to(
                EmployeeRole.SALES,
                from_role=EmployeeRole.POSTVENTA,
                pending="repeat_purchase",
                reason="incident_and_repurchase",
            )
            return _say(
                desk,
                identity,
                conversation,
                (
                    "Anoto el reclamo de postventa. No invento garantía ni devolución: eso lo ve una persona. "
                    f"Si querés repetir la compra, te paso con Adri. Decile la {noun} o el código."
                ),
            )
        conversation.state.pass_to(
            None,
            from_role=EmployeeRole.POSTVENTA,
            pending="human_policy",
            reason="incident",
        )
        return _say(
            desk,
            identity,
            conversation,
            (
                "Anoto el reclamo sobre el pedido. No invento garantía, devolución ni compensación. "
                f"Una persona de {label} puede tomar la política; si querés otra {noun}, Adri arma un pedido nuevo."
            ),
        )

    if wants_sale:
        conversation.state.last_skill = "sales_handoff"
        conversation.state.pass_to(
            EmployeeRole.SALES,
            from_role=EmployeeRole.POSTVENTA,
            pending="repeat_purchase",
            reason="repurchase",
            need=conversation.state.considered_variant_sku,
        )
        if conversation.state.considered_variant_sku:
            found = run_tool(
                runtime,
                identity,
                conversation,
                "catalog.search",
                {"query": conversation.state.considered_variant_sku},
            )
            hits = found.get("hits") or []
            if hits:
                hit = hits[0]
                return _say(
                    desk,
                    identity,
                    conversation,
                    (
                        "Eso es una recompra, no un cobro ni un envío. Te paso con Adri. "
                        f"En catálogo sigue {hit['name']} ({hit['product_sku']}) a {hit['price']} {hit['currency']}."
                    ),
                    {"hits": hits[:3], "price": hit["price"], "sku": hit["product_sku"]},
                )
        return _say(
            desk,
            identity,
            conversation,
            (
                "Puedo pasarte con Adri para una compra nueva. No vendo desde Postventa. "
                f"Decile qué {noun} querés repetir."
            ),
        )

    conversation.state.last_skill = "post_sale_support"
    if conversation.state.order_id:
        return _say(
            desk,
            identity,
            conversation,
            (
                f"Tengo el pedido {conversation.state.order_id} en la carpeta. "
                "Si hay un problema de entrega, lo anoto sin inventar política. Si querés otra unidad, Adri vende."
            ),
        )
    return _say(
        desk,
        identity,
        conversation,
        (
            "Soy Postventa. Contame el pedido o el reclamo con hechos. "
            "No invento garantías; una recompra la toma Adri."
        ),
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
    return render_reply(
        gateway,
        role=identity.role.value,
        context=compile_context(identity, conversation),
        fallback=fallback,
        facts=facts,
    )
