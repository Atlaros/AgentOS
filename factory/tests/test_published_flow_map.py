"""Published canvas map drives the WhatsApp turn graph (docs/00 item 4)."""

from __future__ import annotations

from uuid import uuid4

from factory_os.agents.graph import clear_turn_graphs
from factory_os.domain.flow_canvas import (
    clear_published_flow_maps,
    get_published_flow_kinds,
    publish_flow_map,
)
from factory_os.domain.models import PILOT_TENANT_ID
from factory_os.domain.operator_registry import clear_operator_registry, register_business
from factory_os.domain.tenant_config import clear_memory_tenant_configs, get_tenant_config, put_tenant_config
from factory_os.domain.turn_modules import graph_nodes_for_tenant
from tests.conftest import make_shop, owner_client


def _hit(store, sku: str) -> dict:
    record = store.get_variant(PILOT_TENANT_ID, sku)
    assert record is not None
    return {
        "variant_sku": record.variant_sku,
        "codigo": record.product_sku,
        "name": record.name,
        "price": str(record.price),
        "currency": record.currency,
        "stock": record.stock,
    }


def test_publish_requires_locked_core() -> None:
    clear_published_flow_maps()
    tid = uuid4()
    try:
        publish_flow_map(tid, ("whatsapp", "pedido"))
        assert False, "expected path_locked"
    except ValueError as exc:
        assert str(exc) == "path_locked"


def test_published_map_overrides_modules_for_turn_graph() -> None:
    """Modules without cobros; published map with cobros → turn unlocks Cobros."""
    clear_published_flow_maps()
    clear_memory_tenant_configs()
    modules = ("whatsapp", "pedido", "catalogo")
    assert "cobros" not in graph_nodes_for_tenant(PILOT_TENANT_ID, modules=modules)
    publish_flow_map(PILOT_TENANT_ID, ("whatsapp", "pedido", "cobros", "catalogo"))
    allowed = graph_nodes_for_tenant(PILOT_TENANT_ID, modules=modules)
    assert "cobros" in allowed
    assert "operaciones" in allowed


def test_without_published_map_modules_still_govern() -> None:
    clear_published_flow_maps()
    allowed = graph_nodes_for_tenant(
        uuid4(),
        modules=("whatsapp", "pedido", "catalogo"),
    )
    assert allowed == frozenset({"adri", "postventa"})


def test_run_customer_turn_uses_published_map() -> None:
    """Modules omit cobros; published map includes it → Adri can chain to Cobros."""
    clear_published_flow_maps()
    clear_memory_tenant_configs()
    clear_turn_graphs()
    try:
        put_tenant_config(
            PILOT_TENANT_ID,
            industry="closet",
            modules=("whatsapp", "pedido", "catalogo"),
            name="Thin",
        )
        publish_flow_map(
            PILOT_TENANT_ID,
            ("whatsapp", "pedido", "cobros", "catalogo"),
        )
        runtime = make_shop()
        store = runtime.store
        wa = "59182220001"
        customer = store.get_or_create_customer(PILOT_TENANT_ID, wa)
        conv = store.get_or_create_conversation(PILOT_TENANT_ID, customer)
        hit = _hit(store, "pago1-U-B")
        conv.state.considered_variant_sku = str(hit["variant_sku"])
        conv.state.last_hits = [hit]
        store.save_conversation_state(conv)

        result = runtime.handle_turn(PILOT_TENANT_ID, wa, "me lo llevo")
        conv = store.get_conversation(PILOT_TENANT_ID, conv.id)
        assert conv is not None
        assert conv.state.order_id is not None
        assert conv.state.graph_node == "cobros"
        assert result.role == "collections"
    finally:
        clear_published_flow_maps()
        clear_memory_tenant_configs()
        clear_turn_graphs()


def test_operator_can_publish_flow_map_via_api() -> None:
    clear_published_flow_maps()
    clear_memory_tenant_configs()
    tid = uuid4()
    put_tenant_config(
        tid,
        industry="cafe",
        modules=("whatsapp", "pedido", "cobros"),
        name="API Cafe",
    )
    clear_operator_registry()
    register_business(tid, name="API Cafe", config=get_tenant_config(tid))
    client = owner_client(make_shop())
    response = client.post(
        "/api/operator/flow-map/publish",
        params={"tenant_id": str(tid)},
        json={"kinds": ["whatsapp", "pedido", "cobros", "mostrador"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["published"] is True
    assert set(body["kinds"]) >= {"whatsapp", "pedido", "cobros"}
    assert get_published_flow_kinds(tid) == tuple(body["kinds"])


def test_try_flow_map_validates_without_publishing() -> None:
    from factory_os.domain.flow_canvas import try_flow_map

    clear_published_flow_maps()
    tid = uuid4()
    kinds = try_flow_map(["whatsapp", "pedido", "cobros"])
    assert set(kinds) >= {"pedido", "cobros"}
    assert get_published_flow_kinds(tid) is None
    client = owner_client(make_shop())
    response = client.post(
        "/api/operator/flow-map/try",
        json={"kinds": ["whatsapp", "pedido"]},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "path_locked"


def test_propose_flow_map_does_not_publish() -> None:
    from factory_os.domain.flow_canvas import propose_flow_kinds

    clear_published_flow_maps()
    proposed = propose_flow_kinds(("whatsapp",), palette=("whatsapp", "pedido", "cobros", "caja"))
    assert proposed[:3] == ("whatsapp", "pedido", "cobros")
    assert "caja" in proposed
    client = owner_client(make_shop())
    response = client.post(
        "/api/operator/flow-map/propose",
        json={"kinds": ["whatsapp"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["published"] is False
    assert set(body["proposal"]) >= {"whatsapp", "pedido", "cobros"}
    assert get_published_flow_kinds(uuid4()) is None
