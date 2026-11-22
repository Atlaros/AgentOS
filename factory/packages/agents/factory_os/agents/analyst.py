from __future__ import annotations

from typing import Any

from factory_os.contracts.employees import Identity
from factory_os.domain.analytics_ask import answer_analytics_question
from factory_os.domain.models import Conversation
from factory_os.domain.store import CommerceStore
from factory_os.harness.tools import ToolRuntime


def handle_analyst(
    identity: Identity,
    runtime: ToolRuntime,
    conversation: Conversation,
    text: str,
    gateway: Any,
    *,
    store: CommerceStore,
) -> str:
    _ = runtime
    if conversation.state.channel == "whatsapp":
        return "Analista no atiende el chat de clientes. Pedí métricas por el canal interno."
    conversation.state.last_skill = "business_metrics"
    try:
        answered = answer_analytics_question(store, identity.tenant_id, text, gateway)
    except ValueError:
        return "No pude armar el resumen de Analítica con los hechos del archivo."
    return str(answered["reply"])
