import json
import os
from uuid import uuid4

import pytest

from factory_os.agents.turn import ShopRuntime
from factory_os.domain.catalog import search_catalog
from factory_os.domain.models import PILOT_TENANT_ID, PaymentStatus
from factory_os.domain.postgres import apply_migrations, open_postgres_shop, retain_catalog_skus, seed_catalog
from factory_os.domain.seed import catalog_seed_path, closet_seed_path, extra_seed_paths, pay_test_seed_path
from factory_os.tools.registry import FakePaymentProvider


def _db_url() -> str | None:
    return os.environ.get("FACTORY_OS_TEST_DATABASE_URL")


def test_postgres_catalog_closet() -> None:
    url = _db_url()
    if not url:
        pytest.skip("FACTORY_OS_TEST_DATABASE_URL not set")
    try:
        apply_migrations(url)
        seed = closet_seed_path()
        extras = extra_seed_paths("closet")
        seed_catalog(url, PILOT_TENANT_ID, seed)
        for extra in extras:
            seed_catalog(url, PILOT_TENANT_ID, extra)
        keep = {row["sku"] for row in __import__("json").loads(seed.read_text())["products"]}
        keep |= {row["sku"] for path in extras for row in __import__("json").loads(path.read_text())["products"]}
        retain_catalog_skus(url, PILOT_TENANT_ID, keep)
        store = open_postgres_shop(url, PILOT_TENANT_ID, seed, extra_paths=extras)
    except Exception as exc:
        pytest.skip(f"postgres not reachable: {exc}")
    for order in list(store.list_orders(PILOT_TENANT_ID)):
        store.delete_order(PILOT_TENANT_ID, order.id)
    for payment in list(store.list_payments(PILOT_TENANT_ID)):
        if payment.status is not PaymentStatus.CONFIRMED:
            store.delete_payment(PILOT_TENANT_ID, payment.id)
    hits = search_catalog(store, PILOT_TENANT_ID, "quiero una blusa de seda")
    assert hits
    assert "seda" in hits[0].name.lower()
    vectors = store.list_embeddings()
    assert vectors
    pago = search_catalog(store, PILOT_TENANT_ID, "pago1")
    assert pago and pago[0].codigo == "pago1"
    playbook = store.search_playbook("quiero devolver esta blusa", limit=2)
    assert playbook
    assert playbook[0]["intent"] == "return_request"
    assert len(playbook) <= 2


def test_postgres_order_survives_new_store() -> None:
    url = _db_url()
    if not url:
        pytest.skip("FACTORY_OS_TEST_DATABASE_URL not set")
    try:
        seed = closet_seed_path()
        extras = extra_seed_paths("closet")
        store = open_postgres_shop(url, PILOT_TENANT_ID, seed, extra_paths=extras)
    except Exception as exc:
        pytest.skip(f"postgres not reachable: {exc}")
    shop = ShopRuntime(store, FakePaymentProvider())
    wa = f"5917{uuid4().int % 10000000:07d}"
    shop.handle_turn(PILOT_TENANT_ID, wa, "quiero la blusa pago1")
    shop.handle_turn(PILOT_TENANT_ID, wa, "confirmo")
    again = open_postgres_shop(url, PILOT_TENANT_ID)
    customer = again.get_or_create_customer(PILOT_TENANT_ID, wa)
    conv = again.get_or_create_conversation(PILOT_TENANT_ID, customer)
    assert conv.state.order_id is not None
    assert again.get_order(PILOT_TENANT_ID, conv.state.order_id) is not None


def test_seed_catalog_preserves_live_inventory_quantity() -> None:
    """Restart/reseed must not reset sold units back to the JSON default."""
    url = _db_url()
    if not url:
        pytest.skip("FACTORY_OS_TEST_DATABASE_URL not set")
    try:
        from factory_os.domain.seed import catalog_seed_path

        seed = catalog_seed_path("cafe")
        apply_migrations(url)
        seed_catalog(url, PILOT_TENANT_ID, seed)
        store = open_postgres_shop(url, PILOT_TENANT_ID, seed)
    except Exception as exc:
        pytest.skip(f"postgres not reachable: {exc}")
    sku = "c036"
    store.set_variant_availability(PILOT_TENANT_ID, sku, available=True, stock=7)
    assert store.get_variant(PILOT_TENANT_ID, sku).stock == 7
    seed_catalog(url, PILOT_TENANT_ID, seed)
    again = open_postgres_shop(url, PILOT_TENANT_ID, seed)
    assert again.get_variant(PILOT_TENANT_ID, sku).stock == 7


def test_retain_drops_orphan_closet_variants_on_cafe_skus() -> None:
    """Closet sizes on shared c00x products must not survive a cafe retain."""
    url = _db_url()
    if not url:
        pytest.skip("FACTORY_OS_TEST_DATABASE_URL not set")
    cafe = catalog_seed_path("cafe")
    products = json.loads(cafe.read_text(encoding="utf-8"))["products"]
    keep = {str(row["sku"]) for row in products if row.get("sku")}
    keep_variants = {str(row["variant_sku"]) for row in products if row.get("variant_sku")}
    try:
        apply_migrations(url)
        seed_catalog(url, PILOT_TENANT_ID, closet_seed_path())
        seed_catalog(url, PILOT_TENANT_ID, cafe)
        before = open_postgres_shop(url, PILOT_TENANT_ID)
    except Exception as exc:
        pytest.skip(f"postgres not reachable: {exc}")
    assert before.get_variant(PILOT_TENANT_ID, "c002-42-AC") is not None
    retain_catalog_skus(url, PILOT_TENANT_ID, keep, keep_variants)
    after = open_postgres_shop(url, PILOT_TENANT_ID)
    assert after.get_variant(PILOT_TENANT_ID, "c002-42-AC") is None
    cafe_c002 = after.get_variant(PILOT_TENANT_ID, "c002")
    assert cafe_c002 is not None
    assert cafe_c002.product_sku == "c002"
    assert cafe_c002.variant_sku == "c002"


def test_retain_on_pilot_does_not_drop_other_tenant_products() -> None:
    """Startup retain for the pilot must not delete another business's catalog."""
    from factory_os.domain.postgres import tenant_connection

    url = _db_url()
    if not url:
        pytest.skip("FACTORY_OS_TEST_DATABASE_URL not set")
    other = uuid4()
    cafe = catalog_seed_path("cafe")
    products = json.loads(cafe.read_text(encoding="utf-8"))["products"]
    keep = {str(row["sku"]) for row in products if row.get("sku")}
    keep_variants = {str(row["variant_sku"]) for row in products if row.get("variant_sku")}
    try:
        apply_migrations(url)
        seed_catalog(url, PILOT_TENANT_ID, cafe)
        with tenant_connection(url, other) as conn:
            conn.execute(
                "INSERT INTO tenants (id, name) VALUES (%s, %s) ON CONFLICT (id) DO NOTHING",
                (str(other), "Other"),
            )
            product = conn.execute(
                """
                INSERT INTO products (tenant_id, sku, name, description)
                VALUES (%s, 'other-sku', 'Other item', '')
                ON CONFLICT (tenant_id, sku) DO UPDATE SET name = EXCLUDED.name
                RETURNING id
                """,
                (str(other),),
            ).fetchone()
            conn.execute(
                """
                INSERT INTO product_variants (tenant_id, product_id, sku, attributes)
                VALUES (%s, %s, 'other-sku', '{}'::jsonb)
                ON CONFLICT (tenant_id, sku) DO NOTHING
                """,
                (str(other), product["id"]),
            )
    except Exception as exc:
        pytest.skip(f"postgres not reachable: {exc}")
    retain_catalog_skus(url, PILOT_TENANT_ID, keep, keep_variants)
    with tenant_connection(url, other) as conn:
        row = conn.execute(
            "SELECT sku FROM products WHERE sku = 'other-sku'"
        ).fetchone()
    assert row is not None
    assert row["sku"] == "other-sku"
