"""Conversation summary + durable customer preferences (ADR-002 paso 2).

Facts still come from catalog/shop_knowledge.
Only explicit customer prefs are durable; inferences stay turn-local.
Graph step persistence is WorkingState.graph_node (ADR-004), not this module.
Idle reopen (gap hours) lives here as a turn signal — not a chat wipe.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any

from factory_os.domain.models import Conversation, WorkingState

SUMMARY_THRESHOLD = 12
RECENT_WINDOW = 8
MAX_SUMMARY_CHARS = 800
DEFAULT_IDLE_HOURS = 4.0

_PREF_KEYS = ("budget_max", "size", "color", "occasion", "style")


def idle_hours_threshold() -> float:
    raw = (os.environ.get("CONVERSATION_IDLE_HOURS") or "").strip()
    if not raw:
        return DEFAULT_IDLE_HOURS
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_IDLE_HOURS
    return value if value > 0 else DEFAULT_IDLE_HOURS


def is_idle_reopen(
    last_message_at: datetime | None,
    *,
    hours: float | None = None,
    now: datetime | None = None,
) -> bool:
    """True when the prior message is older than the idle gap. First message → False."""
    if last_message_at is None:
        return False
    gap_h = idle_hours_threshold() if hours is None else hours
    if gap_h <= 0:
        return False
    stamp = last_message_at
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=UTC)
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    return current - stamp >= timedelta(hours=gap_h)


def compact_messages(messages: list[tuple[str, str]], *, max_chars: int = MAX_SUMMARY_CHARS) -> str:
    """Deterministic summary from older turns (pytest-safe; no network)."""
    if not messages:
        return ""
    lines: list[str] = []
    for role, text in messages:
        snippet = " ".join(str(text).split())
        if len(snippet) > 120:
            snippet = snippet[:117] + "…"
        lines.append(f"{role}: {snippet}")
    blob = " | ".join(lines)
    if len(blob) > max_chars:
        blob = blob[: max_chars - 1] + "…"
    return f"resumen: {blob}"


def maybe_refresh_summary(conversation: Conversation) -> bool:
    """Update summary when message count crosses threshold. Returns True if refreshed."""
    total = len(conversation.messages)
    if total < SUMMARY_THRESHOLD:
        return False
    covered = conversation.summary_msg_count or 0
    # Refresh when at least RECENT_WINDOW new messages since last summary.
    if covered > 0 and total - covered < RECENT_WINDOW:
        return False
    older = conversation.messages[: max(0, total - RECENT_WINDOW)]
    if not older:
        return False
    conversation.summary_text = compact_messages(older)
    conversation.summary_msg_count = len(older)
    return True


def prefs_from_working_state(state: WorkingState) -> dict[str, str]:
    """Durable prefs only (customer_explicit provenance)."""
    provenance = state.preference_provenance or {}
    out: dict[str, str] = {}
    for key in _PREF_KEYS:
        if provenance.get(key) != "customer_explicit":
            continue
        value = getattr(state, key, None)
        if value is None or value == "":
            continue
        out[key] = str(value)
    return out


def format_customer_memory(
    *,
    name: str | None = None,
    address: str | None = None,
    prefs: dict[str, str] | None = None,
) -> str:
    parts: list[str] = []
    if name:
        parts.append(f"name={name}")
    if address:
        parts.append(f"address={address}")
    for key in _PREF_KEYS:
        if prefs and prefs.get(key):
            parts.append(f"{key}={prefs[key]}")
    if not parts:
        return ""
    return "customer_memory=" + " ".join(parts)


def format_conversation_summary(summary: str | None) -> str:
    text = (summary or "").strip()
    if not text:
        return ""
    return f"conversation_summary={text}"
