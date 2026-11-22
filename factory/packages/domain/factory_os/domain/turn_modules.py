"""Which WhatsApp graph nodes a tenant's modules / published map unlock."""

from __future__ import annotations

from uuid import UUID

ALL_CUSTOMER_NODES: frozenset[str] = frozenset(
    {"adri", "cobros", "operaciones", "postventa"}
)


def graph_nodes_for_modules(modules: tuple[str, ...] | list[str] | None) -> frozenset[str]:
    """Map enabled business modules (or canvas kinds) to LangGraph employee nodes.

    Empty / None = unrestricted (legacy pilot). Commerce chat needs Adri;
    Cobros unlocks the payment and fulfillment nodes.
    """
    if not modules:
        return ALL_CUSTOMER_NODES
    enabled = {str(item).strip() for item in modules if str(item).strip()}
    nodes: set[str] = set()
    if enabled & {"whatsapp", "pedido", "mostrador", "catalogo"}:
        nodes.update({"adri", "postventa"})
    if "cobros" in enabled:
        nodes.update({"cobros", "operaciones"})
    if not nodes:
        nodes.add("adri")
    return frozenset(nodes)


def graph_nodes_for_tenant(
    tenant_id: UUID,
    *,
    modules: tuple[str, ...] | list[str] | None = None,
    url: str | None = None,
) -> frozenset[str]:
    """Prefer the published canvas map; otherwise fall back to enabled modules."""
    from factory_os.domain.flow_canvas import get_published_flow_kinds

    published = get_published_flow_kinds(tenant_id, url=url)
    if published is not None:
        return graph_nodes_for_modules(published)
    return graph_nodes_for_modules(modules)

