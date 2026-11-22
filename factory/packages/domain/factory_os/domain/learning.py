"""Helpers for public order numbers and conversation learning signals."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from factory_os.domain.models import Conversation
from factory_os.domain.seed import product_code_tokens


def new_public_order_number() -> str:
    """Short customer-facing order id, e.g. AC-A1B2C3D4."""
    return f"AC-{uuid4().hex[:8].upper()}"


def public_number_from_uuid(order_id: UUID) -> str:
    return f"AC-{order_id.hex[:8].upper()}"


def mark_conversation_outcome(
    conversation: Conversation,
    outcome: str,
    *,
    reason: str | None = None,
) -> None:
    """Set durable outcome for continuous improvement (success|abandoned|failed|human_takeover)."""
    conversation.outcome = outcome
    conversation.outcome_reason = reason
    conversation.closed_at = datetime.now(UTC)


def note_live_or_organic(conversation: Conversation, text: str) -> None:
    """Record acquisition source once when a live/product code appears."""
    if conversation.live_code:
        return
    codes = product_code_tokens(text)
    blob = (text or "").lower()
    if codes and ("live" in blob or "tiktok" in blob):
        conversation.source_kind = "live"
        conversation.live_code = codes[0]
    elif codes:
        conversation.source_kind = conversation.source_kind or "organic"
        conversation.live_code = codes[0]
    elif conversation.source_kind is None:
        conversation.source_kind = "organic"
