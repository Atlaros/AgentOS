"""Conversation playbook index (how to sell) — not business facts.

Indexed source: only ``05_playbook_curated.json``. Anti-patterns and raw 01–04
are not indexed. ``example_customer_message`` is never embedded or returned as
a shop fact. Max ``PLAYBOOK_MAX_HITS`` positive hits per turn.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from factory_os.domain.conversation_knowledge import load_playbook
from factory_os.domain.embeddings import cosine, embed_document, embed_documents, embed_query
from factory_os.domain.seed import tokenize

PLAYBOOK_MAX_HITS = 2
PLAYBOOK_VECTOR_MIN = 0.35
PLAYBOOK_DOMAIN = "conversation_behavior"
_STOP = frozenset(
    {
        "a",
        "al",
        "con",
        "de",
        "del",
        "el",
        "en",
        "es",
        "esta",
        "este",
        "la",
        "las",
        "lo",
        "los",
        "me",
        "mi",
        "no",
        "o",
        "para",
        "por",
        "que",
        "se",
        "si",
        "su",
        "te",
        "un",
        "una",
        "y",
        "ya",
    }
)
_QUERY_EXPAND = {
    "barato": {"precio", "cuesta", "barato"},
    "barata": {"precio", "cuesta", "barato"},
    "baratos": {"precio", "cuesta", "barato"},
    "economico": {"precio", "cuesta", "barato"},
    "economica": {"precio", "cuesta", "barato"},
    "devolver": {"devolver", "devolucion", "devoluciones", "return"},
    "devolucion": {"devolver", "devolucion", "devoluciones"},
    "devoluciones": {"devolver", "devolucion", "devoluciones"},
    "cambio": {"cambio", "cambios", "cambiar", "exchange"},
    "cambios": {"cambio", "cambios", "cambiar", "exchange"},
}


@dataclass(frozen=True)
class PlaybookHit:
    pattern_id: str
    intent: str
    situation: str
    next_action: str
    skill: str
    capability: str
    goal: str
    behavior: tuple[str, ...]
    avoid: tuple[str, ...]
    allowed_tools: tuple[str, ...]
    knowledge_sources: tuple[str, ...]
    score: float
    example_is_not_fact: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "pattern_id": self.pattern_id,
            "intent": self.intent,
            "situation": self.situation,
            "next_action": self.next_action,
            "skill": self.skill,
            "capability": self.capability,
            "goal": self.goal,
            "behavior": list(self.behavior),
            "avoid": list(self.avoid),
            "allowed_tools": list(self.allowed_tools),
            "knowledge_sources": list(self.knowledge_sources),
            "score": round(self.score, 4),
            "example_is_not_fact": True,
            "domain": PLAYBOOK_DOMAIN,
        }


def playbook_embed_blob(pattern: dict[str, Any]) -> str:
    """Text to embed. Excludes example messages (never business truth)."""
    parts: list[str] = [
        str(pattern.get("intent") or ""),
        str(pattern.get("situation") or ""),
        str(pattern.get("goal") or ""),
        str(pattern.get("next_action") or ""),
        str(pattern.get("skill") or ""),
        str(pattern.get("capability") or ""),
        str(pattern.get("priority") or ""),
        str(pattern.get("closet_notes") or ""),
    ]
    for key in ("signals", "behavior", "avoid"):
        for item in pattern.get(key) or []:
            parts.append(str(item))
    # Deliberately omit example_customer_message.
    return " ".join(part.strip() for part in parts if part and str(part).strip())


def playbook_payload(pattern: dict[str, Any]) -> dict[str, Any]:
    """JSONB stored in Postgres. Example kept only as non-fact provenance."""
    return {
        "goal": pattern.get("goal") or "",
        "signals": list(pattern.get("signals") or []),
        "behavior": list(pattern.get("behavior") or []),
        "avoid": list(pattern.get("avoid") or []),
        "allowed_tools": list(pattern.get("allowed_tools") or []),
        "knowledge_sources": list(pattern.get("knowledge_sources") or []),
        "priority": pattern.get("priority") or "",
        "closet_notes": pattern.get("closet_notes") or "",
        "example_is_not_fact": True,
        "domain": PLAYBOOK_DOMAIN,
        # Stored for audit only — never returned in format_playbook_hints.
        "example_customer_message": pattern.get("example_customer_message") or "",
    }


def pattern_content_sha(pattern: dict[str, Any]) -> str:
    blob = playbook_embed_blob(pattern)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _hit_from_pattern(pattern: dict[str, Any], score: float) -> PlaybookHit:
    return PlaybookHit(
        pattern_id=str(pattern["pattern_id"]),
        intent=str(pattern.get("intent") or ""),
        situation=str(pattern.get("situation") or ""),
        next_action=str(pattern.get("next_action") or ""),
        skill=str(pattern.get("skill") or ""),
        capability=str(pattern.get("capability") or ""),
        goal=str(pattern.get("goal") or ""),
        behavior=tuple(str(x) for x in (pattern.get("behavior") or [])),
        avoid=tuple(str(x) for x in (pattern.get("avoid") or [])),
        allowed_tools=tuple(str(x) for x in (pattern.get("allowed_tools") or [])),
        knowledge_sources=tuple(str(x) for x in (pattern.get("knowledge_sources") or [])),
        score=float(score),
        example_is_not_fact=True,
    )


def _hit_from_row(row: dict[str, Any], score: float) -> PlaybookHit:
    payload = row.get("payload") or {}
    if not isinstance(payload, dict):
        payload = {}
    return PlaybookHit(
        pattern_id=str(row["pattern_id"]),
        intent=str(row.get("intent") or ""),
        situation=str(row.get("situation") or ""),
        next_action=str(row.get("next_action") or ""),
        skill=str(row.get("skill") or ""),
        capability=str(row.get("capability") or ""),
        goal=str(payload.get("goal") or ""),
        behavior=tuple(str(x) for x in (payload.get("behavior") or [])),
        avoid=tuple(str(x) for x in (payload.get("avoid") or [])),
        allowed_tools=tuple(str(x) for x in (payload.get("allowed_tools") or [])),
        knowledge_sources=tuple(str(x) for x in (payload.get("knowledge_sources") or [])),
        score=float(score),
        example_is_not_fact=True,
    )


def format_playbook_hints(hits: list[PlaybookHit]) -> str:
    """Compact behavior hints for SalesDecision context. Never includes examples."""
    if not hits:
        return ""
    lines = [
        "playbook_hints (behavior only; not price/stock/policy/catalog facts; examples are not facts):"
    ]
    for hit in hits[:PLAYBOOK_MAX_HITS]:
        behave = "; ".join(hit.behavior[:2]) if hit.behavior else ""
        avoid = "; ".join(hit.avoid[:2]) if hit.avoid else ""
        lines.append(
            f"- {hit.pattern_id} intent={hit.intent} action={hit.next_action} "
            f"skill={hit.skill} capability={hit.capability}: {hit.goal}"
        )
        if behave:
            lines.append(f"  do: {behave}")
        if avoid:
            lines.append(f"  avoid: {avoid}")
    return "\n".join(lines)


def _content_tokens(pattern: dict[str, Any]) -> set[str]:
    """Meaningful tokens for lexical match (intent, situation, signals, goal)."""
    parts = [
        str(pattern.get("intent") or "").replace("_", " "),
        str(pattern.get("situation") or "").replace("_", " "),
        str(pattern.get("goal") or ""),
    ]
    for item in pattern.get("signals") or []:
        parts.append(str(item))
    return {tok for tok in tokenize(" ".join(parts)) if tok not in _STOP and len(tok) > 2}


def _query_tokens(query: str) -> set[str]:
    raw = {tok for tok in tokenize(query) if tok not in _STOP}
    expanded = set(raw)
    for tok in raw:
        expanded |= _QUERY_EXPAND.get(tok, set())
    return expanded


@dataclass
class _IndexedPattern:
    pattern: dict[str, Any]
    vector: list[float]
    tokens: set[str]


class PlaybookIndex:
    """In-process index (pytest + fallback when Postgres playbook rows are empty)."""

    def __init__(self) -> None:
        self.rows: list[_IndexedPattern] = []

    def build(self, patterns: list[dict[str, Any]] | None = None) -> int:
        items = patterns if patterns is not None else list(load_playbook()["patterns"])
        blobs = [playbook_embed_blob(item) for item in items]
        vectors = embed_documents(blobs)
        self.rows = [
            _IndexedPattern(pattern=item, vector=vec, tokens=_content_tokens(item))
            for item, vec in zip(items, vectors, strict=True)
        ]
        return len(self.rows)

    def search(self, query: str, *, limit: int = PLAYBOOK_MAX_HITS) -> list[PlaybookHit]:
        if not self.rows:
            return []
        limit = max(1, min(int(limit), PLAYBOOK_MAX_HITS))
        q = (query or "").strip()
        if not q:
            return []
        q_tokens = _query_tokens(q)
        q_vec = embed_query(q)
        scored: list[tuple[float, dict[str, Any]]] = []
        for row in self.rows:
            sim = cosine(q_vec, row.vector)
            overlap = q_tokens & row.tokens
            lexical = float(len(overlap))
            # Intent/situation hits outweigh weak hashed cosine noise.
            score = sim + 0.45 * lexical
            if sim < PLAYBOOK_VECTOR_MIN and lexical < 1:
                continue
            scored.append((score, row.pattern))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [_hit_from_pattern(pattern, score) for score, pattern in scored[:limit]]


@lru_cache(maxsize=1)
def get_playbook_index() -> PlaybookIndex:
    index = PlaybookIndex()
    index.build()
    return index


def search_playbook(
    query: str,
    *,
    limit: int = PLAYBOOK_MAX_HITS,
    store: Any | None = None,
) -> list[PlaybookHit]:
    """Search the curated playbook. Caps at PLAYBOOK_MAX_HITS.

    Uses Postgres kNN when the store exposes ``search_playbook`` and has rows;
    otherwise the in-process index (pytest / empty table fallback).
    """
    cap = max(1, min(int(limit), PLAYBOOK_MAX_HITS))
    if store is not None and hasattr(store, "search_playbook"):
        try:
            rows = store.search_playbook(query, limit=cap)
        except Exception:
            rows = None
        if rows:
            return hits_from_pg_rows(rows)
    return get_playbook_index().search(query, limit=cap)


def playbook_rows_for_seed() -> list[dict[str, Any]]:
    """Rows ready for Postgres upsert (embedding filled by caller)."""
    out: list[dict[str, Any]] = []
    for pattern in load_playbook()["patterns"]:
        blob = playbook_embed_blob(pattern)
        out.append(
            {
                "pattern_id": pattern["pattern_id"],
                "intent": pattern.get("intent") or "",
                "situation": pattern.get("situation") or "",
                "next_action": pattern.get("next_action") or "",
                "skill": pattern.get("skill") or "",
                "capability": pattern.get("capability") or "",
                "payload": playbook_payload(pattern),
                "embed_text": blob,
                "content_sha": pattern_content_sha(pattern),
            }
        )
    return out


def hits_from_pg_rows(rows: list[dict[str, Any]]) -> list[PlaybookHit]:
    hits: list[PlaybookHit] = []
    for row in rows[:PLAYBOOK_MAX_HITS]:
        score = float(row.get("sim") or row.get("score") or 0.0)
        hits.append(_hit_from_row(row, score))
    return hits


def embed_playbook_documents(texts: list[str]) -> list[list[float]]:
    return embed_documents(texts)


def document_embedding(text: str) -> list[float]:
    return embed_document(text)
