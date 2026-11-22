"""Staff-facing chat media transcription / summary (ADR-015 Fase E).

Never confirms payment. Never executes file bytes as code or model instructions.
Production STT/LLM adapters plug into MediaEnricher; tests use FakeMediaEnricher.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Protocol
from uuid import UUID

from factory_os.domain.media import read_media_bytes
from factory_os.domain.models import ConversationMedia

logger = logging.getLogger(__name__)

FAKE_AUDIO_TRANSCRIPT = "Transcripción de prueba (FakeMediaEnricher)."
FAKE_DOCUMENT_SUMMARY = "Resumen de prueba del documento (FakeMediaEnricher)."


@dataclass(frozen=True)
class EnrichmentResult:
    transcript: str | None
    summary: str | None


class MediaEnricher(Protocol):
    def enrich(
        self, kind: str, mime: str | None, filename: str | None, data: bytes
    ) -> EnrichmentResult: ...


class FakeMediaEnricher:
    """Deterministic enricher for tests and local until Deploy wires STT/LLM."""

    def enrich(
        self, kind: str, mime: str | None, filename: str | None, data: bytes
    ) -> EnrichmentResult:
        _ = mime, filename, data  # bytes are never executed
        resolved = (kind or "").strip().lower()
        if resolved == "audio":
            return EnrichmentResult(transcript=FAKE_AUDIO_TRANSCRIPT, summary=None)
        if resolved == "document":
            return EnrichmentResult(transcript=None, summary=FAKE_DOCUMENT_SUMMARY)
        return EnrichmentResult(transcript=None, summary=None)


def enrich_conversation_media(
    store,
    tenant_id: UUID,
    link_id: UUID,
    *,
    enricher: MediaEnricher,
    read_bytes: Callable[[str], bytes] = read_media_bytes,
) -> ConversationMedia | None:
    """Load conversation media + asset, enrich, persist. Staff-facing only."""
    store.require_tenant(tenant_id)
    get_link = getattr(store, "get_conversation_media", None)
    if not callable(get_link):
        return None
    link = get_link(tenant_id, link_id)
    if link is None:
        return None
    if link.status != "ready" or link.asset_id is None:
        return store.update_conversation_media_enrichment(
            tenant_id,
            link_id,
            enrichment_status="failed",
            enrichment_error="not_ready",
        )

    asset = store.get_media_asset(tenant_id, link.asset_id)
    if asset is None:
        return store.update_conversation_media_enrichment(
            tenant_id,
            link_id,
            enrichment_status="failed",
            enrichment_error="missing_asset",
        )

    store.update_conversation_media_enrichment(
        tenant_id,
        link_id,
        enrichment_status="pending",
        enrichment_error=None,
    )
    try:
        data = read_bytes(asset.storage_key)
        result = enricher.enrich(link.kind, link.mime or asset.mime, link.filename, data)
    except Exception as exc:
        logger.warning(
            "media enrichment failed link=%s kind=%s",
            link_id,
            link.kind,
            exc_info=False,
        )
        return store.update_conversation_media_enrichment(
            tenant_id,
            link_id,
            enrichment_status="failed",
            enrichment_error=str(exc)[:120] or "enrich_failed",
        )

    transcript = (result.transcript or "").strip() or None
    summary = (result.summary or "").strip() or None
    if transcript is None and summary is None:
        return store.update_conversation_media_enrichment(
            tenant_id,
            link_id,
            transcript_text=None,
            summary_text=None,
            enrichment_status="none",
            enrichment_error=None,
        )
    return store.update_conversation_media_enrichment(
        tenant_id,
        link_id,
        transcript_text=transcript,
        summary_text=summary,
        enrichment_status="ready",
        enrichment_error=None,
    )
