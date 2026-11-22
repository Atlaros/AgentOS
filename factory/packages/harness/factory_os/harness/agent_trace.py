"""Agent harness observability. Records propose/draft/decision/state — no authz."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import UUID

from factory_os.domain.models import WorkingState

logger = logging.getLogger("factory_os.agent_trace")

_SECRET = re.compile(
    r"(?i)(api[_-]?key|authorization|bearer|password|secret|token)\s*[:=]\s*\S+"
)


def redact(text: str | None) -> str | None:
    if text is None:
        return None
    return _SECRET.sub(r"\1=***", text)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def snapshot_working_state(state: WorkingState) -> dict[str, Any]:
    """Read-only view of commercial desk state for audit."""
    return {
        "stage": state.stage.value,
        "last_action": state.last_action,
        "last_skill": state.last_skill,
        "next_best_action": state.last_action,
        "customer_need": state.customer_need,
        "discovery_asked": state.discovery_asked,
        "budget_max": str(state.budget_max) if state.budget_max is not None else None,
        "size": state.size,
        "color": state.color,
        "occasion": state.occasion,
        "style": state.style,
        "preference_provenance": dict(state.preference_provenance),
        "considered_variant_sku": state.considered_variant_sku,
        "last_hits": list(state.last_hits),
        "cart": list(state.cart),
        "order_id": str(state.order_id) if state.order_id else None,
    }


@dataclass
class AgentTraceEvent:
    conversation_id: str | None
    employee: str | None
    role: str | None
    operation: str
    provider: str | None = None
    model: str | None = None
    timestamp: str = field(default_factory=utc_now)
    latency_ms: int | None = None
    used_fallback: bool | None = None
    prompt: str | None = None
    raw_response: str | None = None
    parsed_action: str | None = None
    parsed_skill: str | None = None
    error: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        data = asdict(self)
        data["prompt"] = redact(self.prompt)
        data["raw_response"] = redact(self.raw_response)
        data["error"] = redact(self.error)
        return data


Sink = Callable[[AgentTraceEvent], None]


class AgentTraceLog:
    """In-memory + optional sink (Postgres). Never stores API keys."""

    def __init__(self, sink: Sink | None = None) -> None:
        self.events: list[AgentTraceEvent] = []
        self._sink = sink
        self._turn: dict[str, str | None] = {
            "conversation_id": None,
            "employee": None,
            "role": None,
        }

    def begin_turn(
        self,
        *,
        conversation_id: str | UUID | None,
        employee: str | None,
        role: str | None,
    ) -> None:
        self._turn = {
            "conversation_id": str(conversation_id) if conversation_id else None,
            "employee": employee,
            "role": role,
        }

    def end_turn(self) -> None:
        self._turn = {"conversation_id": None, "employee": None, "role": None}

    def record(
        self,
        operation: str,
        *,
        provider: str | None = None,
        model: str | None = None,
        latency_ms: int | None = None,
        used_fallback: bool | None = None,
        prompt: str | None = None,
        raw_response: str | None = None,
        parsed_action: str | None = None,
        parsed_skill: str | None = None,
        error: str | None = None,
        payload: dict[str, Any] | None = None,
        conversation_id: str | None = None,
        employee: str | None = None,
        role: str | None = None,
    ) -> AgentTraceEvent:
        event = AgentTraceEvent(
            conversation_id=conversation_id or self._turn.get("conversation_id"),
            employee=employee or self._turn.get("employee"),
            role=role or self._turn.get("role"),
            operation=operation,
            provider=provider,
            model=model,
            latency_ms=latency_ms,
            used_fallback=used_fallback,
            prompt=redact(prompt),
            raw_response=redact(raw_response),
            parsed_action=parsed_action,
            parsed_skill=parsed_skill,
            error=redact(error),
            payload=dict(payload or {}),
        )
        self.events.append(event)
        logger.info("agent_trace %s", json.dumps(event.to_json(), ensure_ascii=False, default=str))
        if self._sink is not None:
            try:
                self._sink(event)
            except Exception as exc:  # noqa: BLE001 — observability must not break turns
                logger.warning("agent_trace sink failed: %s", type(exc).__name__)
        return event

    def for_conversation(self, conversation_id: str) -> list[AgentTraceEvent]:
        wanted = str(conversation_id)
        return [event for event in self.events if event.conversation_id == wanted]


def postgres_trace_sink(url: str) -> Sink:
    """Append-only writer. Uses the service DATABASE_URL (no tenant RLS)."""

    def _write(event: AgentTraceEvent) -> None:
        from psycopg.types.json import Json

        from factory_os.domain.postgres import connect

        data = event.to_json()
        with connect(url) as conn:
            conn.execute(
                """
                INSERT INTO agent_trace_events (
                    conversation_id, employee, role, operation, provider, model,
                    created_at, latency_ms, used_fallback, prompt, raw_response,
                    parsed_action, parsed_skill, error, payload
                ) VALUES (
                    %s, %s, %s, %s, %s, %s,
                    %s::timestamptz, %s, %s, %s, %s,
                    %s, %s, %s, %s
                )
                """,
                (
                    data["conversation_id"],
                    data["employee"],
                    data["role"],
                    data["operation"],
                    data["provider"],
                    data["model"],
                    data["timestamp"],
                    data["latency_ms"],
                    data["used_fallback"],
                    data["prompt"],
                    data["raw_response"],
                    data["parsed_action"],
                    data["parsed_skill"],
                    data["error"],
                    Json(data["payload"]),
                ),
            )
            conn.commit()

    return _write
