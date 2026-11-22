from __future__ import annotations

import re

from factory_os.contracts.employees import Identity
from factory_os.domain.models import Conversation
from factory_os.domain.seed import normalize
from factory_os.harness.tools import ToolRuntime, run_tool

_SKU = re.compile(r"\b(AC-[A-Z0-9-]+|[A-Z]{1,10}\d+[A-Z0-9-]*)\b", re.I)


def handle_suppliers(identity: Identity, runtime: ToolRuntime, conversation: Conversation, text: str) -> str:
    if conversation.state.channel == "whatsapp":
        return "Proveedores no atiende WhatsApp de clientes. Adri vende; el ingreso de stock es interno."
    lowered = normalize(text)
    sku_match = _SKU.search(text)
    if any(word in lowered for word in ("recib", "ingres", "llego mercaderia", "reponer")) and sku_match:
        conversation.state.last_skill = "stock_receive"
        rest = text[: sku_match.start()] + " " + text[sku_match.end() :]
        numbers = [int(item) for item in re.findall(r"\d+", rest)]
        quantity = next((item for item in reversed(numbers) if item >= 1), None)
        if quantity is None:
            return "Para ingresar stock necesito el SKU de variante y una cantidad (por ejemplo recibir h001-M-VP 1)."
        result = run_tool(
            runtime,
            identity,
            conversation,
            "stock.receive",
            {"variant_sku": sku_match.group(1), "quantity": quantity},
            confirmed=True,
        )
        return (
            f"Ingreso de proveedor: +{result['received']} de {result['name']} "
            f"({result['variant_sku']}). Stock ahora {result['stock']}."
        )
    conversation.state.last_skill = "low_stock_alert"
    alert = run_tool(runtime, identity, conversation, "supplier.alert", {})
    low = alert.get("low_stock") or []
    if not low:
        return "No hay SKUs en umbral bajo. El aviso automático al proveedor todavía no está activo."
    lines = ["Stock bajo según el archivo. Todavía no contacto al proveedor (queda para después):"]
    for item in low:
        lines.append(f"- {item['name']} · {item['variant_sku']} · stock {item['stock']}")
    lines.append(alert["note"])
    return "\n".join(lines)
