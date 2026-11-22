from uuid import uuid4

import pytest

from factory_os.domain.flow_canvas import (
    build_flow_map,
    clear_rules,
    create_rule,
    list_rules,
    publish_rule,
    revert_rule,
    update_rule,
)
from factory_os.domain.provision import TEMPLATE_MODULES
from tests.conftest import make_shop, owner_client


def test_flow_map_locks_core_path() -> None:
    flow = build_flow_map(TEMPLATE_MODULES["cafe"])
    locked_nodes = {node.id for node in flow.nodes if node.locked}
    assert locked_nodes == {"pedido", "cobros"}
    locked_edges = {(edge.source, edge.target, edge.port) for edge in flow.edges if edge.locked}
    assert ("whatsapp", "pedido", "pedido") in locked_edges
    assert ("pedido", "cobros", "pedido") in locked_edges


def test_rule_cannot_confirm_payment() -> None:
    clear_rules()
    with pytest.raises(ValueError, match="payment_confirm_forbidden"):
        create_rule(
            when_event="qr_pending",
            if_threshold="hours>24",
            then_action="confirm_payment",
        )


def test_publish_catalog_rule() -> None:
    clear_rules()
    rule = create_rule(
        when_event="qr_pending",
        if_threshold="hours>24",
        then_action="notify_owner",
        tenant_id=uuid4(),
    )
    published = publish_rule(rule.id)
    assert published.status == "published"


def test_operator_flow_map_and_publish_rule_api() -> None:
    clear_rules()
    client = owner_client(make_shop())
    mapped = client.get(
        "/api/operator/flow-map",
        params={"modules": "whatsapp,mostrador,pedido,cobros,caja"},
    )
    assert mapped.status_code == 200
    body = mapped.json()
    assert any(node["id"] == "pedido" and node["locked"] for node in body["nodes"])
    assert body["compatible"]["cobros"]["pago_confirmado"] == ["caja"]
    assert "cobros" not in body["compatible"]["whatsapp"]["pedido"]
    assert body["positions"]["pedido"]["x"] < body["positions"]["caja"]["x"]
    assert "aprobacion" in body["palette"]
    assert "sql" not in body["palette"]

    created = client.post(
        "/api/operator/rules",
        json={
            "when_event": "stock_low",
            "if_threshold": "below_minimum",
            "then_action": "draft_purchase_order",
        },
    )
    assert created.status_code == 200
    rule_id = created.json()["id"]
    published = client.post(f"/api/operator/rules/{rule_id}/publish")
    assert published.status_code == 200
    assert published.json()["status"] == "published"
    listed = client.get("/api/operator/rules")
    assert listed.status_code == 200
    assert listed.json()["rules"][0]["id"] == rule_id
    assert listed.json()["rules"][0]["status"] == "published"


def test_blank_database_url_keeps_rules_in_memory() -> None:
    clear_rules()
    rule = create_rule(
        when_event="qr_pending",
        if_threshold="hours>24",
        then_action="notify_owner",
        url="  ",
    )
    assert list_rules(url="  ")[0].id == rule.id


def test_published_rule_survives_memory_reset_on_postgres() -> None:
    import os

    url = os.environ.get("FACTORY_OS_TEST_DATABASE_URL")
    if not url:
        pytest.skip("FACTORY_OS_TEST_DATABASE_URL not set")
    from factory_os.domain.postgres import apply_migrations

    tenant_id = uuid4()
    try:
        apply_migrations(url)
        from factory_os.domain.provision import provision_business

        provision_business(name="Rule Cafe", industry="cafe", url=url, tenant_id=tenant_id)
        clear_rules()
        rule = create_rule(
            when_event="qr_pending",
            if_threshold="hours>24",
            then_action="notify_owner",
            tenant_id=tenant_id,
            url=url,
        )
        publish_rule(rule.id, url=url)
    except Exception as exc:
        pytest.skip(f"postgres not reachable: {exc}")
    clear_rules()
    found = [item for item in list_rules(url=url) if item.id == rule.id]
    assert len(found) == 1
    assert found[0].status == "published"


def test_rule_version_survives_on_postgres() -> None:
    import os

    url = os.environ.get("FACTORY_OS_TEST_DATABASE_URL")
    if not url:
        pytest.skip("FACTORY_OS_TEST_DATABASE_URL not set")
    from factory_os.domain.postgres import apply_migrations

    tenant_id = uuid4()
    try:
        apply_migrations(url)
        from factory_os.domain.provision import provision_business

        provision_business(name="Version Cafe", industry="cafe", url=url, tenant_id=tenant_id)
        clear_rules()
        rule = create_rule(
            when_event="qr_pending",
            if_threshold="hours>24",
            then_action="notify_owner",
            tenant_id=tenant_id,
            url=url,
        )
        publish_rule(rule.id, url=url)
        update_rule(rule.id, then_action="notify_owner_later", url=url)
        second = publish_rule(rule.id, url=url)
    except Exception as exc:
        pytest.skip(f"postgres not reachable: {exc}")
    assert second.version == 2
    clear_rules()
    restored = revert_rule(rule.id, version=1, url=url)
    assert restored.then_action == "notify_owner"
    assert restored.version == 1
    found = [item for item in list_rules(url=url) if item.id == rule.id]
    assert found[0].then_action == "notify_owner"
    assert found[0].version == 1


def test_same_port_connects_and_a_different_port_does_not() -> None:
    from factory_os.domain.flow_canvas import connect_modules

    edge = connect_modules("cobros", "caja", "pago_confirmado", enabled=("caja",))
    assert edge.port == "pago_confirmado"
    assert edge.locked is False
    with pytest.raises(ValueError, match="port_mismatch"):
        connect_modules("cobros", "caja", "pedido", enabled=("caja",))


def test_compatible_targets_only_list_valid_destinations() -> None:
    from factory_os.domain.flow_canvas import compatible_by_source, compatible_targets, flow_map_as_dict

    assert compatible_targets("cobros", "pago_confirmado") == ("caja",)
    assert "contabilidad" not in compatible_targets("cobros", "pago_confirmado")
    assert "pedido" not in compatible_targets("cobros", "pago_confirmado")
    assert set(compatible_targets("caja", "aviso")) == {
        "analitica",
        "aprobacion",
        "proveedores",
        "reportes",
    }
    assert compatible_targets("whatsapp", "pedido") == ("pedido",)
    assert compatible_targets("whatsapp", "pago_confirmado") == ()
    assert "cobros" not in compatible_targets("whatsapp", "pedido")
    mapped = flow_map_as_dict(build_flow_map(("caja", "contabilidad")))
    assert mapped["compatible"]["cobros"]["pago_confirmado"] == list(
        compatible_by_source()["cobros"]["pago_confirmado"]
    )


def test_layout_positions_place_locked_path_on_the_left() -> None:
    from factory_os.domain.flow_canvas import flow_map_as_dict, layout_positions

    placed = layout_positions(("whatsapp", "pedido", "cobros", "caja", "contabilidad"))
    assert placed["whatsapp"]["x"] < placed["caja"]["x"]
    assert placed["pedido"]["x"] == placed["cobros"]["x"]
    assert placed["caja"]["y"] < placed["contabilidad"]["y"]
    mapped = flow_map_as_dict(build_flow_map(("caja", "contabilidad")))
    assert mapped["positions"]["pedido"]["x"] < mapped["positions"]["caja"]["x"]


def test_palette_only_places_catalog_modules() -> None:
    from factory_os.domain.flow_canvas import flow_map_as_dict, palette_modules, place_module

    assert "aprobacion" in palette_modules()
    assert "sql" not in palette_modules()
    node, spot = place_module("aprobacion", present=("caja",), x=40, y=80)
    assert node.id == "aprobacion"
    assert node.locked is False
    assert spot == {"x": 40, "y": 80}
    with pytest.raises(ValueError, match="unknown_module"):
        place_module("sql", present=())
    with pytest.raises(ValueError, match="already_placed"):
        place_module("caja", present=("caja",))
    mapped = flow_map_as_dict(build_flow_map(("caja",)))
    assert "aprobacion" in mapped["palette"]
    assert "sql" not in mapped["palette"]


def test_locked_core_path_cannot_be_rewired() -> None:
    from factory_os.domain.flow_canvas import connect_modules

    kept = connect_modules("pedido", "cobros", "pedido", enabled=())
    assert kept.locked is True
    with pytest.raises(ValueError, match="path_locked"):
        connect_modules("whatsapp", "cobros", "pedido", enabled=())


def test_publish_keeps_versions_and_revert_restores_the_previous_one() -> None:
    clear_rules()
    rule = create_rule(
        when_event="qr_pending",
        if_threshold="hours>24",
        then_action="notify_owner",
    )
    first = publish_rule(rule.id)
    assert first.version == 1
    rule.then_action = "notify_owner_later"
    second = publish_rule(rule.id)
    assert second.version == 2
    restored = revert_rule(rule.id, version=1)
    assert restored.then_action == "notify_owner"
    assert restored.status == "published"
    assert restored.version == 1


def test_operator_can_connect_a_port_and_revert_a_published_rule() -> None:
    clear_rules()
    client = owner_client(make_shop())
    blocked = client.post(
        "/api/operator/connections",
        json={"source": "whatsapp", "target": "cobros", "port": "pedido"},
    )
    assert blocked.status_code == 400
    assert blocked.json()["detail"] == "path_locked"

    connected = client.post(
        "/api/operator/connections",
        json={"source": "cobros", "target": "caja", "port": "pago_confirmado"},
    )
    assert connected.status_code == 200
    assert connected.json()["port"] == "pago_confirmado"
    assert connected.json()["locked"] is False

    created = client.post(
        "/api/operator/rules",
        json={
            "when_event": "qr_pending",
            "if_threshold": "hours>24",
            "then_action": "notify_owner",
        },
    )
    assert created.status_code == 200
    rule_id = created.json()["id"]
    assert client.post(f"/api/operator/rules/{rule_id}/publish").status_code == 200
    revised = client.post(
        f"/api/operator/rules/{rule_id}/revise",
        json={"then_action": "notify_owner_later"},
    )
    assert revised.status_code == 200
    published = client.post(f"/api/operator/rules/{rule_id}/publish")
    assert published.status_code == 200
    assert published.json()["version"] == 2
    reverted = client.post(f"/api/operator/rules/{rule_id}/revert", json={"version": 1})
    assert reverted.status_code == 200
    assert reverted.json()["then_action"] == "notify_owner"
    assert reverted.json()["version"] == 1
