from factory_os.domain.operator_registry import clear_operator_registry, list_businesses
from factory_os.domain.provision import provision_business
from tests.conftest import make_shop, owner_client


def test_provision_registers_business_for_operator() -> None:
    clear_operator_registry()
    tid = provision_business(name="Mi Cafe", industry="cafe")
    rows = list_businesses()
    assert len(rows) == 1
    assert rows[0].tenant_id == tid
    assert rows[0].industry == "cafe"
    assert rows[0].name == "Mi Cafe"


def test_blank_database_url_keeps_the_memory_registry() -> None:
    clear_operator_registry()
    provision_business(name="Mi Cafe", industry="cafe")
    rows = list_businesses(url="  ")
    assert len(rows) == 1
    assert rows[0].name == "Mi Cafe"


def test_operator_businesses_endpoint_lists_provisioned() -> None:
    clear_operator_registry()
    provision_business(name="Tienda Ropa", industry="ropa")
    client = owner_client(make_shop())
    response = client.get("/api/operator/businesses")
    assert response.status_code == 200
    body = response.json()
    assert len(body["businesses"]) == 1
    assert body["businesses"][0]["name"] == "Tienda Ropa"
    assert body["businesses"][0]["industry"] == "ropa"
    assert body["businesses"][0]["whatsapp_status"] == "not_connected"
    assert body["businesses"][0]["cost"] is None
    payment = next(
        item for item in body["businesses"][0]["autonomy"] if item["action"] == "confirm_payment"
    )
    assert payment["level"] == "never"


def test_live_whatsapp_and_published_rule_show_on_the_console() -> None:
    from factory_os.domain.flow_canvas import clear_rules
    from factory_os.domain.models import PILOT_TENANT_ID
    from tests.conftest import api_settings

    clear_operator_registry()
    clear_rules()
    provision_business(name="Pilot", industry="cafe", tenant_id=PILOT_TENANT_ID)
    provision_business(name="Otra", industry="ropa")
    client = owner_client(
        make_shop(),
        api_settings(
            meta_whatsapp_access_token="token",
            meta_whatsapp_phone_number_id="phone",
        ),
    )
    created = client.post(
        "/api/operator/rules",
        json={
            "when_event": "qr_pending",
            "if_threshold": "hours>24",
            "then_action": "notify_owner",
        },
    )
    assert created.status_code == 200
    published = client.post(f"/api/operator/rules/{created.json()['id']}/publish")
    assert published.status_code == 200
    rows = {row["name"]: row for row in client.get("/api/operator/businesses").json()["businesses"]}
    assert rows["Pilot"]["whatsapp_status"] == "connected"
    assert rows["Pilot"]["version"] == "published"
    assert rows["Pilot"]["cost"] is None
    assert rows["Otra"]["whatsapp_status"] == "not_connected"
    assert rows["Otra"]["version"] == "draft"


def test_operator_list_survives_memory_reset_on_postgres() -> None:
    import os
    from uuid import uuid4

    import pytest

    url = os.environ.get("FACTORY_OS_TEST_DATABASE_URL")
    if not url:
        pytest.skip("FACTORY_OS_TEST_DATABASE_URL not set")
    from factory_os.domain.postgres import apply_migrations

    clear_operator_registry()
    tenant_id = uuid4()
    try:
        apply_migrations(url)
        provision_business(name="Persist Cafe", industry="cafe", url=url, tenant_id=tenant_id)
    except Exception as exc:
        pytest.skip(f"postgres not reachable: {exc}")
    clear_operator_registry()
    rows = [row for row in list_businesses(url=url) if row.tenant_id == tenant_id]
    assert len(rows) == 1
    assert rows[0].name == "Persist Cafe"
    assert rows[0].industry == "cafe"
    assert rows[0].modules[0] == "whatsapp"


def test_operator_can_provision_a_business_from_the_console() -> None:
    clear_operator_registry()
    client = owner_client(make_shop())
    response = client.post(
        "/api/operator/businesses",
        json={"name": "Taller Norte", "industry": "ropa"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Taller Norte"
    assert body["industry"] == "ropa"
    assert "tenant_id" in body
    assert "owner_email" not in body
    listed = {row["name"]: row for row in client.get("/api/operator/businesses").json()["businesses"]}
    assert "Taller Norte" in listed
    bad = client.post(
        "/api/operator/businesses",
        json={"name": "X", "industry": "taller"},
    )
    assert bad.status_code == 400


def test_operator_can_tighten_autonomy_for_a_business() -> None:
    from factory_os.domain.autonomy import clear_tenant_autonomy

    clear_operator_registry()
    clear_tenant_autonomy()
    tid = provision_business(name="Tight Cafe", industry="cafe")
    client = owner_client(make_shop())
    response = client.post(
        "/api/operator/autonomy",
        json={"tenant_id": str(tid), "action": "adjust_stock", "level": "never"},
    )
    assert response.status_code == 200
    stock = next(
        item for item in response.json()["autonomy"] if item["action"] == "adjust_stock"
    )
    assert stock["level"] == "never"
    listed = {
        row["name"]: row for row in client.get("/api/operator/businesses").json()["businesses"]
    }
    listed_stock = next(
        item for item in listed["Tight Cafe"]["autonomy"] if item["action"] == "adjust_stock"
    )
    assert listed_stock["level"] == "never"
    denied = client.post(
        "/api/operator/autonomy",
        json={"tenant_id": str(tid), "action": "confirm_payment", "level": "within_limits"},
    )
    assert denied.status_code == 400


def test_operator_console_shows_model_tokens_when_metered() -> None:
    from factory_os.domain.model_usage import clear_model_usage, record_model_tokens

    clear_operator_registry()
    clear_model_usage()
    tid = provision_business(name="Metered Cafe", industry="cafe")
    record_model_tokens(tid, 42)
    client = owner_client(make_shop())
    rows = {row["name"]: row for row in client.get("/api/operator/businesses").json()["businesses"]}
    assert rows["Metered Cafe"]["cost"] == "42 tokens"


def test_missing_usage_table_keeps_tokens_in_memory(monkeypatch) -> None:
    import psycopg
    from uuid import uuid4

    from factory_os.domain.model_usage import (
        clear_model_usage,
        cost_label,
        record_model_tokens,
    )

    clear_model_usage()

    def fail(_url: str):
        raise psycopg.errors.UndefinedTable("model_usage")

    monkeypatch.setattr("factory_os.domain.postgres.connect", fail)
    tid = uuid4()
    record_model_tokens(tid, 7, url="postgresql://unused")
    assert cost_label(tid, url="postgresql://unused") == "7 tokens"


def test_model_usage_survives_a_memory_reset_on_postgres() -> None:
    import os
    from uuid import uuid4

    import pytest

    from factory_os.domain.model_usage import clear_model_usage, cost_label, record_model_tokens
    from factory_os.domain.postgres import apply_migrations
    from factory_os.domain.provision import provision_business

    url = os.environ.get("FACTORY_OS_TEST_DATABASE_URL")
    if not url:
        pytest.skip("FACTORY_OS_TEST_DATABASE_URL not set")
    clear_model_usage()
    tenant_id = uuid4()
    try:
        apply_migrations(url)
        provision_business(name="Usage Luna", industry="cafe", url=url, tenant_id=tenant_id)
        record_model_tokens(tenant_id, 15, url=url)
    except Exception as exc:
        pytest.skip(f"postgres not reachable: {exc}")
    clear_model_usage()
    assert cost_label(tenant_id) is None
    assert cost_label(tenant_id, url=url) == "15 tokens"


def test_operator_diagnosis_reports_gaps() -> None:
    client = owner_client(make_shop())
    response = client.get(
        "/api/operator/diagnosis",
        params={"industry": "cafe", "modules": "whatsapp,pedido,cobros"},
    )
    assert response.status_code == 200
    body = response.json()
    by_id = {row["process_id"]: row for row in body["processes"]}
    assert by_id["wa_order"]["status"] == "covered"
    assert by_id["bar_queue"]["status"] == "gap"
    assert by_id["bar_queue"]["gaps"] == ["barra"]
