"""Active modules drive the flow map, panel nav payload, and API access."""

from __future__ import annotations

from uuid import uuid4

from factory_os.domain.models import PILOT_TENANT_ID
from factory_os.domain.operator_registry import clear_operator_registry, register_business
from factory_os.domain.tenant_config import clear_memory_tenant_configs, put_tenant_config
from tests.conftest import make_shop, owner_client


def test_flow_map_for_tenant_uses_its_modules_not_a_fixed_list() -> None:
    clear_operator_registry()
    clear_memory_tenant_configs()
    tid = uuid4()
    config = put_tenant_config(
        tid,
        industry="cafe",
        modules=("whatsapp", "pedido", "cobros"),
        name="Thin Cafe",
    )
    register_business(tid, name="Thin Cafe", config=config)
    client = owner_client(make_shop())

    mapped = client.get("/api/operator/flow-map", params={"tenant_id": str(tid)})
    assert mapped.status_code == 200
    kinds = {node["id"] for node in mapped.json()["nodes"]}
    assert "cobros" in kinds
    assert "pedido" in kinds
    assert "caja" not in kinds
    assert "contabilidad" not in kinds
    assert "proveedores" not in kinds


def test_flow_map_unknown_tenant_is_404() -> None:
    clear_operator_registry()
    client = owner_client(make_shop())
    missing = client.get("/api/operator/flow-map", params={"tenant_id": str(uuid4())})
    assert missing.status_code == 404
    assert missing.json()["detail"] == "tenant_not_found"


def test_disabled_module_api_is_404_when_tenant_lists_modules() -> None:
    clear_memory_tenant_configs()
    put_tenant_config(
        PILOT_TENANT_ID,
        industry="cafe",
        modules=("whatsapp", "pedido", "cobros", "catalogo"),
        name="Pilot",
    )
    client = owner_client(make_shop())
    blocked = client.get("/api/cash")
    assert blocked.status_code == 404
    assert blocked.json()["detail"] == "module_disabled"
    allowed = client.get("/api/orders")
    assert allowed.status_code == 200


def test_empty_modules_keep_legacy_pilot_unrestricted() -> None:
    clear_memory_tenant_configs()
    client = owner_client(make_shop())
    cash = client.get("/api/cash")
    assert cash.status_code == 200
    shop = client.get("/api/shop/modules")
    assert shop.status_code == 200
    assert shop.json()["modules"] is None
    assert shop.json()["nav_hrefs"] is None


def test_shop_modules_lists_nav_for_restricted_tenant() -> None:
    clear_memory_tenant_configs()
    put_tenant_config(
        PILOT_TENANT_ID,
        industry="cafe",
        modules=("caja", "conocimiento"),
        name="Pilot",
    )
    client = owner_client(make_shop())
    shop = client.get("/api/shop/modules")
    assert shop.status_code == 200
    body = shop.json()
    assert set(body["modules"]) == {"caja", "conocimiento"}
    assert set(body["nav_hrefs"]) == {"/cash", "/knowledge"}
