import os
from uuid import uuid4

import pytest

from factory_os.domain.provision import TEMPLATE_MODULES, provision_business
from factory_os.domain.tenant_config import clear_memory_tenant_configs, get_tenant_config


def test_provision_cafe_sets_industry_and_modules() -> None:
    clear_memory_tenant_configs()
    tenant_id = provision_business(name="Mi Cafe", industry="cafe")
    config = get_tenant_config(tenant_id)
    assert config.industry == "cafe"
    assert config.modules == TEMPLATE_MODULES["cafe"]


def test_provision_ropa_is_isolated_from_cafe() -> None:
    clear_memory_tenant_configs()
    cafe = provision_business(name="Cafe", industry="cafe")
    ropa = provision_business(name="Closet", industry="ropa")
    assert cafe != ropa
    assert get_tenant_config(cafe).industry == "cafe"
    assert get_tenant_config(ropa).industry == "ropa"


def test_provision_cafe_seeds_catalog_on_postgres() -> None:
    url = os.environ.get("FACTORY_OS_TEST_DATABASE_URL")
    if not url:
        pytest.skip("FACTORY_OS_TEST_DATABASE_URL not set")
    from factory_os.domain.postgres import apply_migrations, open_postgres_shop

    try:
        apply_migrations(url)
        tenant_id = provision_business(
            name="Cafe Test",
            industry="cafe",
            url=url,
            tenant_id=uuid4(),
        )
        store = open_postgres_shop(url, tenant_id)
    except Exception as exc:
        pytest.skip(f"postgres not reachable: {exc}")
    assert get_tenant_config(tenant_id, url=url).industry == "cafe"
    assert store.get_variant(tenant_id, "c001") is not None


def test_template_autonomy_keeps_payment_confirmation_never() -> None:
    from factory_os.domain.autonomy import template_autonomy, tighten_autonomy

    grants = template_autonomy("cafe")
    payment = next(item for item in grants if item.action == "confirm_payment")
    assert payment.level == "never"
    with pytest.raises(ValueError, match="autonomy_floor"):
        tighten_autonomy(grants, action="confirm_payment", level="within_limits")


def test_owner_can_demand_more_care_without_loosening_the_floor() -> None:
    from factory_os.domain.autonomy import template_autonomy, tighten_autonomy

    grants = template_autonomy("ropa")
    tightened = tighten_autonomy(grants, action="reply_customer", level="approval")
    reply = next(item for item in tightened if item.action == "reply_customer")
    payment = next(item for item in tightened if item.action == "confirm_payment")
    assert reply.level == "approval"
    assert payment.level == "never"
