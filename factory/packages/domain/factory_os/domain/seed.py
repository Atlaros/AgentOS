from __future__ import annotations

import json
import re
import unicodedata
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from factory_os.domain.store import MemoryCommerceStore, VariantRecord

_TOKEN = re.compile(r"[a-z0-9]+")
# Closet codes are letter(s)+digits (pago1, h001). Clients often type "pago 1".
_CODE_TOKEN = re.compile(r"^[a-z]{1,10}\d+$")
# Spaced form: short prefix only (pago/h/p/s), not Spanish words + numbers ("tienen 20").
_SPACED_CODE = re.compile(r"\b([a-z]{1,5})\s+(\d{1,6})\b")
_SPACED_CODE_STOP = frozenset(
    {
        "de",
        "del",
        "el",
        "la",
        "las",
        "los",
        "un",
        "una",
        "unos",
        "en",
        "al",
        "mi",
        "tu",
        "su",
        "es",
        "si",
        "no",
        "me",
        "te",
        "se",
        "lo",
        "le",
        "ya",
        "o",
        "y",
        "a",
        "por",
        "para",
        "con",
        "sin",
        "mas",
        "muy",
        "hay",
        "son",
        "fue",
        "ser",
        "esta",
        "este",
        "eso",
        "que",
        "como",
        "todo",
        "hola",
    }
)


def normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return decomposed.encode("ascii", "ignore").decode("ascii").lower()


def tokenize(text: str) -> set[str]:
    return set(_TOKEN.findall(normalize(text)))


def product_code_tokens(text: str) -> list[str]:
    """Catalog códigos in customer text, including spaced forms like 'pago 1' → pago1.

    Order follows first appearance in the normalized text (stable; not set order).
    """
    norm = normalize(text)
    found: list[tuple[int, str]] = []
    seen: set[str] = set()
    for match in _SPACED_CODE.finditer(norm):
        letters, digits = match.group(1), match.group(2)
        if letters in _SPACED_CODE_STOP:
            continue
        code = f"{letters}{digits}"
        if code in seen or not _CODE_TOKEN.match(code):
            continue
        seen.add(code)
        found.append((match.start(), code))
    for match in _TOKEN.finditer(norm):
        token = match.group(0)
        if token in seen or not _CODE_TOKEN.match(token):
            continue
        seen.add(token)
        found.append((match.start(), token))
    found.sort(key=lambda item: item[0])
    return [code for _, code in found]


def catalog_search_blob(row: dict, attrs: dict) -> str:
    """Public catalog text for pgvector. No cost, barcode, secrets, or credentials."""
    skip = {
        "precio_costo",
        "Precio_costo",
        "barcode",
        "codigo_barras",
        "password",
        "secret",
        "api_key",
        "token",
        "database_url",
    }
    safe_attrs = {key: value for key, value in attrs.items() if key not in skip}
    return " ".join(
        [
            row.get("name") or "",
            row.get("description") or "",
            str(safe_attrs.get("category") or row.get("category") or ""),
            str(safe_attrs.get("subcategory") or ""),
            str(safe_attrs.get("color") or ""),
            str(safe_attrs.get("talla") or ""),
            str(safe_attrs.get("material") or ""),
            str(safe_attrs.get("style") or ""),
            str(safe_attrs.get("brand") or ""),
            str(safe_attrs.get("codigo") or ""),
            str(safe_attrs.get("codigo_referencia") or ""),
            row.get("sku") or row.get("product_sku") or "",
            row.get("variant_sku") or "",
        ]
    )


def load_catalog_json(path: Path, store: MemoryCommerceStore) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    tenant_id = UUID(payload["tenant_id"])
    store.require_tenant(tenant_id)
    _load_catalog_products(store, payload)


def load_catalog_for_store(store: MemoryCommerceStore, path: Path) -> None:
    """Load product rows into this store. The file's tenant id is not the store's."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    _load_catalog_products(store, payload)


def _load_catalog_products(store: MemoryCommerceStore, payload: dict) -> None:
    from factory_os.domain.embeddings import embed_document

    for row in payload["products"]:
        attrs = dict(row.get("attributes") or {})
        blob = catalog_search_blob(row, attrs)
        record = VariantRecord(
            product_sku=row["sku"],
            variant_sku=row["variant_sku"],
            name=row["name"],
            description=row.get("description") or "",
            category=str(attrs.get("category") or ""),
            attributes=attrs,
            price=Decimal(str(row["amount"])),
            currency=row.get("currency") or "BOB",
            stock=int(row.get("available_quantity") or 0),
            tokens=tokenize(blob),
        )
        store.upsert_variant(record)
        store.put_embedding(record.variant_sku, embed_document(blob))


def _seeds_dir() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        seeds = parent / "db" / "seeds"
        if seeds.is_dir():
            return seeds
    raise FileNotFoundError("db/seeds")


def default_seed_path() -> Path:
    """Excel Closet catalog. Prefer `load_pilot_catalog` to also include pago1–pago4."""
    return closet_seed_path()


def closet_seed_path() -> Path:
    return _seeds_dir() / "catalog_closet.json"


def pay_test_seed_path() -> Path:
    return _seeds_dir() / "catalog_pay_test.json"


def extra_seed_paths(kind: str = "closet") -> list[Path]:
    """Pilot overlay: pago1–pago4 only for the Closet catalog."""
    if kind.strip().lower() != "closet":
        return []
    path = pay_test_seed_path()
    return [path] if path.exists() else []


def load_pilot_catalog(store: MemoryCommerceStore) -> None:
    """Load the live catalog: Excel Closet + pago1–pago4. No inventadas."""
    load_catalog_json(closet_seed_path(), store)
    for path in extra_seed_paths("closet"):
        load_catalog_json(path, store)


_CATALOG_SEED_FILES = {
    "closet": "catalog_closet.json",
    "cafe": "catalog_cafe.json",
    "pay_test": "catalog_pay_test.json",
}


def catalog_seed_path(kind: str = "closet") -> Path:
    """Resolve a named catalog seed. Missing files and unknown kinds fail closed."""
    key = (kind or "closet").strip().lower()
    filename = _CATALOG_SEED_FILES.get(key)
    if filename is None:
        raise FileNotFoundError(f"unknown catalog seed '{kind}'")
    path = _seeds_dir() / filename
    if not path.exists():
        raise FileNotFoundError(f"{filename} required")
    return path
