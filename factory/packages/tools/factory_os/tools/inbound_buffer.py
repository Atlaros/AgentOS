"""Coalesce rapid WhatsApp messages from the same number before one turn."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Protocol

from factory_os.tools.inbound_dedup import claim_identity

logger = logging.getLogger(__name__)

DEFAULT_DEBOUNCE_S = 8.0


class InboundBuffer(Protocol):
    def coalesce(
        self,
        wa_number: str,
        text: str,
        *,
        debounce_s: float = DEFAULT_DEBOUNCE_S,
        tenant_id: str | None = None,
    ) -> str | None:
        """Return joined text if this caller should run the turn; None if superseded."""


class MemoryInboundBuffer:
    """Process-local debounce. debounce_s=0 flushes immediately (pytest)."""

    def __init__(self) -> None:
        self._bufs: dict[str, list[str]] = {}
        self._tokens: dict[str, str] = {}

    def coalesce(
        self,
        wa_number: str,
        text: str,
        *,
        debounce_s: float = DEFAULT_DEBOUNCE_S,
        tenant_id: str | None = None,
    ) -> str | None:
        key = wa_number.strip()
        if not key:
            return text
        identity = claim_identity(key, tenant_id)
        self._bufs.setdefault(identity, []).append(text)
        token = str(uuid.uuid4())
        self._tokens[identity] = token
        if debounce_s > 0:
            time.sleep(debounce_s)
        if self._tokens.get(identity) != token:
            return None
        joined = "\n".join(self._bufs.pop(identity, []))
        self._tokens.pop(identity, None)
        return joined


class RedisInboundBuffer:
    def __init__(self, url: str) -> None:
        import redis

        self._client = redis.Redis.from_url(url, decode_responses=True)
        self._client.ping()

    def coalesce(
        self,
        wa_number: str,
        text: str,
        *,
        debounce_s: float = DEFAULT_DEBOUNCE_S,
        tenant_id: str | None = None,
    ) -> str | None:
        key = wa_number.strip()
        if not key:
            return text
        identity = claim_identity(key, tenant_id)
        buf_key = f"wa:buf:{identity}"
        tok_key = f"wa:buf:tok:{identity}"
        token = str(uuid.uuid4())
        pipe = self._client.pipeline()
        pipe.rpush(buf_key, text)
        pipe.expire(buf_key, 120)
        pipe.set(tok_key, token, ex=120)
        pipe.execute()
        if debounce_s > 0:
            time.sleep(debounce_s)
        if self._client.get(tok_key) != token:
            return None
        msgs = self._client.lrange(buf_key, 0, -1) or []
        self._client.delete(buf_key, tok_key)
        return "\n".join(str(m) for m in msgs)


def build_inbound_buffer(*, redis_url: str = "", memory: MemoryInboundBuffer | None = None) -> InboundBuffer:
    if redis_url:
        try:
            return RedisInboundBuffer(redis_url)
        except Exception:
            logger.warning("Redis inbound buffer unavailable; using memory", exc_info=True)
    return memory or MemoryInboundBuffer()
