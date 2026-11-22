from decimal import Decimal
from pathlib import Path

from factory_os.domain.catalog import search_catalog
from factory_os.domain.catalog_xlsx import build_catalog_payload, make_variant_sku, placeholder_image
from factory_os.domain.models import PILOT_TENANT_ID
from factory_os.domain.seed import closet_seed_path, extra_seed_paths, load_catalog_json
from factory_os.domain.store import MemoryCommerceStore


def test_generated_sku_uses_id_size_color() -> None:
    used: set[str] = set()
    sku = make_variant_sku("h001", "m", "verde pistacho", used)
    assert sku == "h001-M-VP"
    clash = make_variant_sku("h001", "m", "verde pistacho", used)
    assert clash == "h001-M-VP2"


def test_excel_rows_skip_cost_barcode_and_override() -> None:
    payload = build_catalog_payload(
        [
            {
                "id_producto": "h001",
                "codigo_referencia": "h001",
                "nombre": "blusa de hilo jubenil",
                "categoria": "blusas",
                "subcategoria": "hilo",
                "marca": "hk80",
                "descripcion": "escote en v",
                "Precio_costo": "80",
                "precio_base_bs": "145",
                "material": "hilo",
                "temporada": "primavera-verano",
                "estilo": "Casual",
            }
        ],
        [
            {
                "id_producto": "h001",
                "sku": "",
                "talla": "m",
                "color": "verde pistacho",
                "precio_override_bs": "99",
                "stock": "1",
                "codigo_barras": "123",
                "imagen_url": "",
            }
        ],
    )
    row = payload["products"][0]
    assert row["sku"] == "h001"
    assert row["variant_sku"] == "h001-M-VP"
    assert row["amount"] == "145.00"
    assert row["attributes"]["codigo"] == "h001"
    assert "precio_costo" not in row["attributes"]
    assert "barcode" not in row["attributes"]
    assert "codigo_barras" not in row["attributes"]
    assert row["attributes"]["image_url"] == placeholder_image("h001")


def test_sold_excel_row_is_disabled_and_not_searched() -> None:
    payload = build_catalog_payload(
        [
            {
                "id_producto": "j022",
                "nombre": "pantalon jean",
                "categoria": "pantalon",
                "precio_base_bs": "210",
                "vendido": "si",
            }
        ],
        [
            {
                "id_producto": "j022",
                "talla": "40",
                "color": "azul claro",
                "stock": "1",
            }
        ],
    )
    row = payload["products"][0]
    assert row["available_quantity"] == 0
    assert row["attributes"]["disabled"] is True

    store = MemoryCommerceStore(PILOT_TENANT_ID)
    load_catalog_json(closet_seed_path(), store)
    sold = search_catalog(store, PILOT_TENANT_ID, "j022")
    assert all(hit.codigo != "j022" for hit in sold)
    jeans = search_catalog(store, PILOT_TENANT_ID, "pantalon jean")
    assert all(hit.codigo != "j022" for hit in jeans)


def test_closet_seed_finds_h001_by_product_id() -> None:
    path = closet_seed_path()
    assert path.exists()
    store = MemoryCommerceStore(PILOT_TENANT_ID)
    load_catalog_json(path, store)
    hits = search_catalog(store, PILOT_TENANT_ID, "h001")
    assert hits
    assert hits[0].codigo == "h001"
    assert hits[0].product_sku == "h001"
    assert hits[0].score == 10.0
    assert hits[0].variant_sku.startswith("h001-")
    blob = path.read_text(encoding="utf-8")
    assert "Precio_costo" not in blob
    assert "codigo_barras" not in blob
    assert Path(path).stat().st_size > 0


def test_pay_test_blouses_are_one_bob() -> None:
    store = MemoryCommerceStore(PILOT_TENANT_ID)
    load_catalog_json(closet_seed_path(), store)
    for extra in extra_seed_paths("closet"):
        load_catalog_json(extra, store)
    for code in ("pago1", "pago2", "pago3", "pago4"):
        hits = search_catalog(store, PILOT_TENANT_ID, code)
        assert hits
        assert hits[0].codigo == code
        assert hits[0].price == Decimal("1.00")
        assert hits[0].category == "blusas"


def test_blusas_query_returns_named_blouses_not_random_category() -> None:
    from factory_os.domain.seed import normalize

    store = MemoryCommerceStore(PILOT_TENANT_ID)
    load_catalog_json(closet_seed_path(), store)
    hits = search_catalog(store, PILOT_TENANT_ID, "estoy buscando blusas")
    assert hits
    assert "blusa" in hits[0].name.lower()
    names = [normalize(hit.name) for hit in hits]
    assert len(set(names)) == len(names)
    assert any("seda" in name or "hilo" in name or "corset" in name for name in names)
