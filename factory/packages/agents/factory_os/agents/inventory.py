from __future__ import annotations

import re

from factory_os.contracts.employees import Identity
from factory_os.domain.models import Conversation
from factory_os.domain.seed import normalize
from factory_os.harness.tools import ToolRuntime, run_tool

_SKU = re.compile(r"\b(AC-[A-Z0-9-]+|[A-Z]{1,10}\d+[A-Z0-9-]*)\b", re.I)
_DELTA = re.compile(r"([+-]?\d+)\s*(?:unidades|u)?")


def handle_inventory(identity: Identity, runtime: ToolRuntime, conversation: Conversation, text: str) -> str:
    if conversation.state.channel == "whatsapp":
        return "Inventario no atiende el chat de clientes. Adri informa stock de venta."
    lowered = normalize(text)
    sku_match = _SKU.search(text)

    if "ajust" in lowered and sku_match:
        conversation.state.last_skill = "inventory_adjustment"
        numbers = [int(item) for item in _DELTA.findall(text) if item.lstrip("+-").isdigit()]
        delta = numbers[-1] if numbers else None
        if delta is None:
            return "Para ajustar necesito el SKU de variante y un delta (por ejemplo -1 o +2)."
        result = run_tool(
            runtime,
            identity,
            conversation,
            "inventory.adjust",
            {"variant_sku": sku_match.group(1), "delta": delta},
            confirmed=True,
        )
        return f"Stock actualizado: {result['name']} · {result['variant_sku']} · stock {result['stock']}."

    conversation.state.last_skill = "low_stock" if "bajo" in lowered or "low" in lowered else "stock_inquiry"
    query = sku_match.group(1) if sku_match else text
    found = run_tool(runtime, identity, conversation, "catalog.search", {"query": query})
    hits = found.get("hits") or []
    if not hits:
        return "No hay esa variante en el catálogo estructurado. No invento stock."
    if "bajo" in lowered:
        low = [hit for hit in hits if int(hit["stock"]) <= 1]
        rows = low or hits[:3]
        lines = ["Stock bajo (umbral 1) según el archivo:"]
        for hit in rows:
            lines.append(f"- {hit['name']} · stock {hit['stock']} · {hit['variant_sku']}")
        return "\n".join(lines)
    hit = hits[0]
    return (
        f"{hit['name']} · stock {hit['stock']} · {hit['price']} {hit['currency']} · {hit['variant_sku']}. "
        "Cantidad del store, no estimada."
    )
