from pathlib import Path
from decimal import Decimal

import pytest

from factory_os.domain.catalog import search_catalog
from factory_os.domain.models import PILOT_TENANT_ID
from factory_os.domain.seed import load_pilot_catalog
from factory_os.domain.store import MemoryCommerceStore


def _store() -> MemoryCommerceStore:
    store = MemoryCommerceStore(PILOT_TENANT_ID)
    load_pilot_catalog(store)
    return store


def test_seda_hits_real_sku() -> None:
    hits = search_catalog(_store(), PILOT_TENANT_ID, "quiero una blusa de seda")
    assert hits
    assert "seda" in hits[0].name.lower()
    assert hits[0].product_sku.startswith("s")


def test_elegante_returns_existing_sku_not_invented() -> None:
    store = _store()
    known = {record.product_sku for record in store.variants.values()}
    hits = search_catalog(store, PILOT_TENANT_ID, "blusa tipo corset")
    assert hits
    assert hits[0].product_sku in known
    assert "corset" in hits[0].name.lower()


def test_hybrid_query_still_real_sku() -> None:
    store = _store()
    assert store.list_embeddings()
    known = {record.product_sku for record in store.variants.values()}
    hits = search_catalog(store, PILOT_TENANT_ID, "blusa de hilo")
    assert hits
    assert all(hit.product_sku in known for hit in hits)


def test_empty_embeddings_fall_back_to_lexical() -> None:
    store = _store()
    store.embeddings.clear()
    hits = search_catalog(store, PILOT_TENANT_ID, "pantalon jean")
    assert hits
    assert "jean" in hits[0].name.lower()


def test_hashed_embedding_matches_catalog_dims() -> None:
    from factory_os.domain.embeddings import cosine, embed_dims, hashed_embedding

    left = hashed_embedding("blusa de seda verde")
    right = hashed_embedding("blusa de seda verde")
    assert len(left) == embed_dims()
    assert left == right
    assert cosine(left, right) == pytest.approx(1.0)


def test_unknown_query_is_empty() -> None:
    hits = search_catalog(_store(), PILOT_TENANT_ID, "nave espacial de titanio")
    assert hits == []


def test_vector_recall_reads_inventory_then_sql_facts() -> None:
    """pgvector can surface a neighbor with no token overlap; price still comes from the row."""
    from factory_os.domain.embeddings import hashed_embedding

    store = _store()
    sample = next(record for record in store.iter_variants() if record.attributes.get("codigo") == "h001")
    store.put_embedding(sample.variant_sku, hashed_embedding("qwxzblorp narglewick"))
    hits = search_catalog(store, PILOT_TENANT_ID, "qwxzblorp narglewick")
    assert hits
    assert hits[0].product_sku == sample.product_sku
    assert hits[0].price == sample.price
    assert hits[0].stock == sample.stock


def test_budget_search_returns_items_at_or_under_ceiling() -> None:
    from factory_os.domain.catalog import parse_budget

    assert parse_budget("tiene alguna cueste 150 bs?") == Decimal("150")
    hits = search_catalog(_store(), PILOT_TENANT_ID, "tiene alguna cueste 150 bs?")
    assert hits
    assert all(hit.price <= Decimal("150") for hit in hits)


def test_pago1_exact_code_is_one_bob() -> None:
    hits = search_catalog(_store(), PILOT_TENANT_ID, "pago1")
    assert hits
    assert hits[0].codigo == "pago1"
    assert hits[0].price == Decimal("1.00")


def test_migrations_declare_view_and_rls() -> None:
    root = Path(__file__).resolve().parents[1]
    commerce = (root / "db/migrations/001_commerce.sql").read_text(encoding="utf-8")
    rls = (root / "db/migrations/002_rls.sql").read_text(encoding="utf-8")
    cash = (root / "db/migrations/004_cash.sql").read_text(encoding="utf-8")
    assert "CREATE VIEW agent_catalog_read" in commerce
    assert "CREATE TABLE product_embeddings" in commerce
    assert "vector(64)" in commerce
    assert "ENABLE ROW LEVEL SECURITY" in rls
    assert "cash_movements" in cash
