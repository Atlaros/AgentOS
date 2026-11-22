"""Claim inbound WhatsApp message ids so Meta retries do not re-run the turn."""

from __future__ import annotations

import logging
from typing import Protocol

logger = logging.getLogger(__name__)

_REDIS_TTL_S = 86_400


def claim_identity(message_id: str, tenant_id: str | None) -> str:
    """Claim key. Tenant-scoped when the runtime passes a tenant; otherwise the bare id."""
    key = message_id.strip()
    tenant = (tenant_id or "").strip()
    if not tenant:
        return key
    return f"{tenant}:{key}"


class InboundDeduper(Protocol):
    def claim(self, message_id: str, *, wa_number: str = "", tenant_id: str | None = None) -> bool:
        """Return True if this message_id is new and claimed. False if duplicate."""


class MemoryInboundDeduper:
    """Process-local claim. Used in pytest and when Redis/Postgres are unavailable."""

    def __init__(self) -> None:
        self._seen: set[str] = set()

    def claim(self, message_id: str, *, wa_number: str = "", tenant_id: str | None = None) -> bool:
        _ = wa_number
        key = message_id.strip()
        if not key:
            return True
        identity = claim_identity(key, tenant_id)
        if identity in self._seen:
            return False
        self._seen.add(identity)
        return True


class RedisInboundDeduper:
    def __init__(self, url: str) -> None:
        import redis

        self._client = redis.Redis.from_url(url, decode_responses=True)
        self._client.ping()

    def claim(self, message_id: str, *, wa_number: str = "", tenant_id: str | None = None) -> bool:
        _ = wa_number
        key = message_id.strip()
        if not key:
            return True
        ok = self._client.set(
            f"wa:msg:{claim_identity(key, tenant_id)}",
            "1",
            nx=True,
            ex=_REDIS_TTL_S,
        )
        return bool(ok)


class PostgresInboundDeduper:
    def __init__(self, database_url: str) -> None:
        self._url = database_url

    def claim(self, message_id: str, *, wa_number: str = "", tenant_id: str | None = None) -> bool:
        import psycopg

        from factory_os.domain.models import PILOT_TENANT_ID

        key = message_id.strip()
        if not key:
            return True
        tenant = (tenant_id or "").strip() or str(PILOT_TENANT_ID)
        with psycopg.connect(self._url) as conn:
            conn.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant,))
            row = conn.execute(
                """
                INSERT INTO whatsapp_inbound_events (message_id, tenant_id, wa_number)
                VALUES (%s, %s::uuid, %s)
                ON CONFLICT (tenant_id, message_id) DO NOTHING
                RETURNING message_id
                """,
                (key, tenant, wa_number or None),
            ).fetchone()
            conn.commit()
        return row is not None


class ChainedInboundDeduper:
    """Redis first (fast reject), then Postgres (durable). Memory fills gaps in tests."""

    def __init__(self, *layers: InboundDeduper) -> None:
        self._layers = layers

    def claim(self, message_id: str, *, wa_number: str = "", tenant_id: str | None = None) -> bool:
        key = message_id.strip()
        if not key:
            return True
        # All layers must accept; first reject wins (duplicate).
        for layer in self._layers:
            try:
                if not layer.claim(key, wa_number=wa_number, tenant_id=tenant_id):
                    return False
            except Exception:
                logger.exception("inbound dedup layer failed; continuing", extra={"layer": type(layer).__name__})
        return True


def build_inbound_deduper(
    *,
    redis_url: str = "",
    database_url: str = "",
    memory: MemoryInboundDeduper | None = None,
) -> InboundDeduper:
    layers: list[InboundDeduper] = []
    if redis_url:
        try:
            layers.append(RedisInboundDeduper(redis_url))
        except Exception:
            logger.warning("Redis inbound dedup unavailable; skipping", exc_info=True)
    if database_url:
        try:
            layers.append(PostgresInboundDeduper(database_url))
        except Exception:
            logger.warning("Postgres inbound dedup unavailable; skipping", exc_info=True)
    if not layers:
        return memory or MemoryInboundDeduper()
    if memory is not None:
        layers.insert(0, memory)
    return ChainedInboundDeduper(*layers) if len(layers) > 1 else layers[0]
