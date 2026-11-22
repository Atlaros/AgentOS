from __future__ import annotations

import re
from decimal import Decimal

from factory_os.contracts.employees import Identity
from factory_os.domain.models import Conversation
from factory_os.domain.seed import normalize
from factory_os.harness.tools import ToolRuntime, run_tool

_SKU = re.compile(r"\b(AC-[A-Z0-9-]+)\b", re.I)
_PRICE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:bob)?", re.I)


def handle_catalog_admin(identity: Identity, runtime: ToolRuntime, conversation: Conversation, text: str) -> str:
    if conversation.state.channel == "whatsapp":
        return "Catálogo no atiende WhatsApp de clientes."
    lowered = normalize(text)
    sku_match = _SKU.search(text)

    if any(word in lowered for word in ("desactiv", "disable", "baja")) and sku_match:
        conversation.state.last_skill = "product_disable"
        result = run_tool(
            runtime,
            identity,
            conversation,
            "catalog.disable",
            {"variant_sku": sku_match.group(1).upper()},
            confirmed=True,
        )
        return f"Variante desactivada: {result['variant_sku']}."

    if any(word in lowered for word in ("alta", "crear", "nuevo", "upsert", "actualizar", "editar", "precio")):
        conversation.state.last_skill = "product_create" if "crear" in lowered or "alta" in lowered else "product_update"
        variant_sku = sku_match.group(1).upper() if sku_match else "AC-STAFF-NEW-001"
        prices = _PRICE.findall(text)
        payload = {
            "variant_sku": variant_sku,
            "product_sku": variant_sku.rsplit("-", 1)[0] if "-" in variant_sku else variant_sku,
            "name": "Ficha staff" if "crear" in lowered or "alta" in lowered else None,
            "price": prices[-1] if prices else None,
            "stock": 1,
        }
        payload = {key: value for key, value in payload.items() if value is not None}
        if "name" not in payload:
            payload["name"] = f"Producto {variant_sku}"
        if "price" not in payload:
            payload["price"] = str(Decimal("10"))
        result = run_tool(runtime, identity, conversation, "catalog.upsert", payload, confirmed=True)
        return (
            f"Catálogo actualizado: {result['name']} · {result['variant_sku']} · "
            f"{result['price']} · stock {result['stock']}."
        )

    conversation.state.last_skill = "catalog_maintenance"
    query = sku_match.group(1) if sku_match else text
    found = run_tool(runtime, identity, conversation, "catalog.search", {"query": query})
    hits = found.get("hits") or []
    if not hits:
        return "No encontré esa ficha. No invento un producto."
    hit = hits[0]
    return f"Ficha: {hit['name']} · {hit['product_sku']} · {hit['price']} {hit['currency']} · stock {hit['stock']}."
