from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from factory_os.domain.embeddings import cosine, embed_query
from factory_os.domain.models import CatalogHit
from factory_os.domain.seed import normalize, product_code_tokens, tokenize
from factory_os.domain.store import CommerceStore, VariantRecord

EMBED_WEIGHT = 2.0
# Hashed 64-d cosine of unrelated text sits ~0.18; neighbors we keep are above this.
VECTOR_MIN = 0.45
VECTOR_CANDIDATES = 40

STOP = frozenset(
    {
        "el",
        "la",
        "los",
        "las",
        "de",
        "del",
        "un",
        "una",
        "unos",
        "unas",
        "algo",
        "quiero",
        "me",
        "para",
        "por",
        "y",
        "o",
        "en",
        "con",
        "mi",
        "tu",
        "dame",
        "busco",
        "buscando",
        "busca",
        "necesito",
        "estoy",
        "estas",
        "esta",
        "hay",
        "tiene",
        "tienen",
        "alguna",
        "alguno",
        "algunos",
        "algunas",
        "quisiera",
        "mostrar",
        "mostrame",
        "ver",
        "venden",
        "cueste",
        "cuesta",
    }
)

EXPAND = {
    "elegante": frozenset({"floral", "midi", "vestido"}),
    "fiesta": frozenset({"floral", "midi", "vestido"}),
    "boda": frozenset({"floral", "midi", "vestido", "fiesta"}),
    "crepe": frozenset({"crepe", "blusa"}),
    "crepre": frozenset({"crepe", "blusa"}),
    "regalo": frozenset({"blusa", "vestido"}),
    "regalarle": frozenset({"blusa", "vestido"}),
    "esposa": frozenset({"blusa", "vestido"}),
}
_CHEAP = frozenset({"economico", "economica", "barato", "barata"})
_BUDGET = re.compile(r"(\d+(?:[.,]\d{1,2})?)\s*(bs|bob|bolivianos?)\b")
_GARMENT = {
    "blusa": "blusas",
    "blusas": "blusa",
    "vestido": "vestidos",
    "vestidos": "vestido",
    "falda": "faldas",
    "faldas": "falda",
    "short": "shorts",
    "shorts": "short",
    "jean": "jeans",
    "jeans": "jean",
    "pantalon": "pantalones",
    "pantalones": "pantalon",
    "polera": "poleras",
    "poleras": "polera",
    "top": "tops",
    "tops": "top",
}
_GARMENT_ROOTS = frozenset(
    {"blusa", "vestido", "falda", "short", "jean", "pantalon", "polera", "top"}
)


def parse_budget(query: str) -> Decimal | None:
    """Client-stated ceiling in BOB/Bs. Not a discount."""
    match = _BUDGET.search(normalize(query))
    if not match:
        return None
    raw = match.group(1).replace(",", ".")
    try:
        amount = Decimal(raw)
    except InvalidOperation:
        return None
    if amount <= 0:
        return None
    return amount


def fold_tokens(tokens: set[str]) -> set[str]:
    """Plural/singular garment and simple -s/-es stems so blusas hits blusa."""
    out = set(tokens)
    for token in tokens:
        pair = _GARMENT.get(token)
        if pair:
            out.add(pair)
        if token.endswith("es") and len(token) > 4:
            out.add(token[:-2])
        elif token.endswith("s") and len(token) > 3:
            out.add(token[:-1])
    return out


def expand_query(tokens: set[str]) -> set[str]:
    out = fold_tokens(tokens)
    for token in list(out):
        out |= EXPAND.get(token, frozenset())
    return out


def score_variant(query_tokens: set[str], record: VariantRecord, query_norm: str) -> float:
    if not query_tokens:
        return 0.0
    codigo = normalize(str(record.attributes.get("codigo") or ""))
    if codigo and (codigo in query_tokens or query_norm == codigo):
        return 10.0
    sku_norm = normalize(record.product_sku)
    variant_norm = normalize(record.variant_sku)
    if sku_norm in query_tokens or variant_norm in query_tokens or query_norm in {sku_norm, variant_norm}:
        return 8.0
    name_tokens = fold_tokens(tokenize(record.name))
    cat_tokens = fold_tokens(
        tokenize(record.category or "") | tokenize(str(record.attributes.get("subcategory") or ""))
    )
    name_overlap = query_tokens & name_tokens
    cat_overlap = query_tokens & cat_tokens
    blob_overlap = query_tokens & fold_tokens(record.tokens)
    if not name_overlap and not cat_overlap and not blob_overlap:
        return 0.0
    score = 0.0
    distinctive = name_overlap - _GARMENT_ROOTS
    garment_in_name = name_overlap & _GARMENT_ROOTS
    if distinctive:
        score += 5.0 + 2.0 * len(distinctive)
    if garment_in_name:
        score += 4.0 + 1.5 * len(garment_in_name)
    if cat_overlap:
        score += 1.0 if name_overlap else 0.8
    extra = blob_overlap - name_overlap - cat_overlap
    if extra:
        score += min(1.0, 0.2 * len(extra))
    return score


def store_embeddings(store: CommerceStore) -> dict[str, list[float]]:
    getter = getattr(store, "list_embeddings", None)
    if not callable(getter):
        return {}
    data = getter()
    return dict(data) if data else {}


def _diversify(ranked: list[tuple[float, float, VariantRecord]], limit: int) -> list[tuple[float, float, VariantRecord]]:
    seen: set[str] = set()
    out: list[tuple[float, float, VariantRecord]] = []
    for item in ranked:
        key = normalize(item[2].name)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
        if len(out) >= limit:
            break
    return out


def _query_similarities(store: CommerceStore, query_vec: list[float]) -> dict[str, float]:
    """pgvector kNN when the store has it; otherwise cosine over loaded embeddings."""
    nearest = getattr(store, "similar_variants", None)
    if callable(nearest):
        try:
            return dict(nearest(query_vec, VECTOR_CANDIDATES))
        except TypeError:
            return dict(nearest(query_vec))
    embeddings = store_embeddings(store)
    return {sku: cosine(query_vec, vec) for sku, vec in embeddings.items()}


def _exact_product_ref(record: VariantRecord, query_norm: str, raw_tokens: set[str]) -> bool:
    """True when the customer named this variant's codigo or SKU (not a category browse)."""
    codigo = normalize(str(record.attributes.get("codigo") or ""))
    sku = normalize(record.product_sku)
    variant = normalize(record.variant_sku)
    if query_norm in {codigo, sku, variant}:
        return True
    named = raw_tokens | set(product_code_tokens(query_norm))
    return bool(named & {codigo, sku, variant} - {""})


def search_catalog(
    store: CommerceStore,
    tenant_id,
    query: str,
    limit: int = 5,
    *,
    budget_max: Decimal | None = None,
    filters: dict[str, str] | None = None,
    include_test_only: bool = False,
) -> list[CatalogHit]:
    """READ the sellable inventory (facts + pgvector), then rank. Never invents price/SKU.

    test_only variants are hidden unless the query names their exact codigo/SKU (T13).
    budget_max / filters come from SalesDecision when provided (T9).
    """
    store.require_tenant(tenant_id)
    from factory_os.domain.order_hold import release_expired_unpaid_orders

    release_expired_unpaid_orders(store, tenant_id)
    held = store.held_variant_skus(tenant_id)
    raw_tokens = (tokenize(query) - STOP) | set(product_code_tokens(query))
    tokens = expand_query(raw_tokens)
    query_norm = normalize(query)
    budget = budget_max if budget_max is not None else parse_budget(query)
    cheap = bool(raw_tokens & _CHEAP) or budget is not None
    filt = {normalize(k): normalize(str(v)) for k, v in (filters or {}).items() if v}
    query_vec = embed_query(query.strip() or query_norm)
    similar = _query_similarities(store, query_vec)
    ranked: list[tuple[float, float, VariantRecord]] = []
    named_codes = set(product_code_tokens(query))
    for record in store.iter_variants():
        if record.attributes.get("disabled") or record.stock < 1:
            continue
        if record.variant_sku in held:
            continue
        if record.attributes.get("test_only") and not include_test_only:
            if not _exact_product_ref(record, query_norm, raw_tokens):
                continue
        lexical = score_variant(tokens, record, query_norm)
        if filt and not _matches_filters(record, filt):
            continue
        sim = float(similar.get(record.variant_sku) or 0.0)
        in_budget = budget is not None and record.price <= budget
        if lexical <= 0 and not in_budget and sim < VECTOR_MIN:
            continue
        ranked.append((lexical + EMBED_WEIGHT * sim, lexical, record))
    ranked.sort(
        key=lambda item: (
            0
            if normalize(str(item[2].attributes.get("codigo") or "")) in named_codes
            else 1,
            0 if budget is not None and item[2].price <= budget else 1,
            item[2].price if cheap else Decimal("0"),
            -item[0],
            -item[1],
            0 if normalize(item[2].product_sku) == query_norm else 1,
        )
    )
    hits: list[CatalogHit] = []
    for _hybrid, lexical, record in _diversify(ranked, limit):
        hits.append(
            CatalogHit(
                product_sku=record.product_sku,
                variant_sku=record.variant_sku,
                name=record.name,
                description=record.description,
                category=record.category,
                attributes=dict(record.attributes),
                price=record.price,
                currency=record.currency,
                stock=record.stock,
                codigo=str(record.attributes.get("codigo") or ""),
                score=float(lexical),
            )
        )
    return hits


PRODUCT_RAG_MAX = 5
_PRODUCT_RAG_ATTRS = ("color", "talla", "size", "material", "style", "brand", "subcategory")


def format_product_rag(hits: list[CatalogHit], *, limit: int = PRODUCT_RAG_MAX) -> str:
    """Public product cards for propose context. Never price, stock, cost, or secrets."""
    if not hits:
        return ""
    lines = ["product_rag:"]
    for hit in hits[: max(1, limit)]:
        attrs = hit.attributes or {}
        bits: list[str] = [hit.name]
        if hit.codigo:
            bits.append(f"codigo={hit.codigo}")
        if hit.category:
            bits.append(f"category={hit.category}")
        for key in _PRODUCT_RAG_ATTRS:
            value = attrs.get(key)
            if value and str(value).strip():
                label = "talla" if key == "size" else key
                bits.append(f"{label}={value}")
        desc = " ".join(str(hit.description or "").split())
        if desc:
            if len(desc) > 80:
                desc = desc[:77] + "…"
            bits.append(f"desc={desc}")
        lines.append("  - " + " | ".join(bits))
    return "\n".join(lines)


def _matches_filters(record: VariantRecord, filt: dict[str, str]) -> bool:
    """Soft attribute filters from SalesDecision (color, size/talla, category)."""
    attrs = {normalize(str(k)): normalize(str(v)) for k, v in record.attributes.items()}
    category = normalize(record.category or "")
    for key, wanted in filt.items():
        if not wanted:
            continue
        if key in {"category", "categoria"}:
            if wanted not in category and wanted not in attrs.get("category", ""):
                return False
            continue
        if key in {"size", "talla"}:
            got = attrs.get("talla") or attrs.get("size") or ""
            if wanted not in got and got not in wanted:
                return False
            continue
        if key in {"color", "colour"}:
            got = attrs.get("color") or ""
            if wanted not in got and got not in wanted:
                return False
            continue
        got = attrs.get(key) or ""
        if got and wanted not in got and got not in wanted:
            return False
    return True


def hit_to_dict(hit: CatalogHit) -> dict:
    return {
        "product_sku": hit.product_sku,
        "variant_sku": hit.variant_sku,
        "name": hit.name,
        "price": str(hit.price),
        "currency": hit.currency,
        "stock": hit.stock,
        "codigo": hit.codigo,
        "talla": str(hit.attributes.get("talla") or ""),
        "color": str(hit.attributes.get("color") or ""),
        "image_url": str(hit.attributes.get("image_url") or ""),
        "score": hit.score,
    }
