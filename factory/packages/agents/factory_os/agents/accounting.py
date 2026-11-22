from __future__ import annotations

import re
from decimal import Decimal

from factory_os.contracts.employees import Identity
from factory_os.domain.models import Conversation
from factory_os.domain.seed import normalize
from factory_os.harness.tools import ToolRuntime, run_tool

_AMOUNT = re.compile(r"(\d+(?:[.,]\d+)?)")


def handle_accounting(identity: Identity, runtime: ToolRuntime, conversation: Conversation, text: str) -> str:
    if conversation.state.channel == "whatsapp":
        return "Contabilidad no atiende WhatsApp de clientes. Cobros cobra el QR."
    lowered = normalize(text)
    if any(word in lowered for word in ("qr", "cobrar", "pague")):
        return (
            "Eso es Cobros, no caja. Contabilidad registra el flujo interno de dinero; "
            "el QR del cliente lo emite y confirma Cobros con el adaptador."
        )
    if any(word in lowered for word in ("libro", "arqueo", "saldo", "flujo", "caja")) and not any(
        word in lowered for word in ("entrada", "salida", "ingreso", "egreso", "gasto")
    ):
        conversation.state.last_skill = "cash_ledger"
        ledger = run_tool(runtime, identity, conversation, "cash.ledger", {})
        return (
            f"Caja: entradas {ledger['in']} · salidas {ledger['out']} · saldo {ledger['balance']} "
            f"({ledger['count']} movimientos). {ledger['note']}"
        )
    direction = None
    if any(word in lowered for word in ("entrada", "ingreso", "deposito")):
        direction = "in"
        conversation.state.last_skill = "cash_in"
    elif any(word in lowered for word in ("salida", "egreso", "gasto", "retiro")):
        direction = "out"
        conversation.state.last_skill = "cash_out"
    if direction:
        match = _AMOUNT.search(text.replace(",", "."))
        if not match:
            return "Indicá el monto (por ejemplo: entrada 50 o salida 20 gasto)."
        amount = Decimal(match.group(1))
        result = run_tool(
            runtime,
            identity,
            conversation,
            "cash.record",
            {"direction": direction, "amount": str(amount), "reason": text, "currency": "BOB"},
            confirmed=True,
        )
        verb = "Entrada" if direction == "in" else "Salida"
        return f"{verb} de caja {result['amount']} {result['currency']} registrada. No es un cobro QR."
    conversation.state.last_skill = "cash_ledger"
    return (
        "Soy Contabilidad. Registro caja (entrada/salida/arqueo). "
        "No emito QR: eso es Cobros."
    )
