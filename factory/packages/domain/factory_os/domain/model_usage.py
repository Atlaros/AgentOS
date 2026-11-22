"""Per-business model token totals for the operator console (ADR-021)."""

from __future__ import annotations

from uuid import UUID

_TOKENS: dict[UUID, int] = {}
_USAGE_LOADED = False


def clear_model_usage() -> None:
    global _USAGE_LOADED
    _TOKENS.clear()
    _USAGE_LOADED = False


def record_model_tokens(tenant_id: UUID, tokens: int, *, url: str | None = None) -> None:
    """Add tokens for one business. Non-positive counts are ignored."""
    if tokens < 1:
        return
    load_model_usage(url)
    _TOKENS[tenant_id] = _TOKENS.get(tenant_id, 0) + int(tokens)
    _persist_tokens(url, tenant_id, _TOKENS[tenant_id])


def tokens_for(tenant_id: UUID, *, url: str | None = None) -> int:
    load_model_usage(url)
    return _TOKENS.get(tenant_id, 0)


def cost_label(tenant_id: UUID, *, url: str | None = None) -> str | None:
    """Human label for the console. None when this business has no metered use."""
    total = tokens_for(tenant_id, url=url)
    if total < 1:
        return None
    return f"{total} tokens"


def load_model_usage(url: str | None) -> None:
    """Fill token totals from the database. A missing table leaves memory as it is."""
    global _USAGE_LOADED
    database = (url or "").strip()
    if not database or _USAGE_LOADED:
        return
    from factory_os.domain.postgres import connect

    try:
        conn = connect(database)
    except Exception as exc:
        if _missing_relation(exc):
            return
        raise
    try:
        rows = conn.execute("SELECT tenant_id, tokens FROM model_usage").fetchall()
    except Exception as exc:
        if _missing_relation(exc):
            return
        raise
    finally:
        conn.close()
    for row in rows:
        tenant_id = row["tenant_id"] if isinstance(row["tenant_id"], UUID) else UUID(str(row["tenant_id"]))
        _TOKENS[tenant_id] = int(row.get("tokens") or 0)
    _USAGE_LOADED = True


def _persist_tokens(url: str | None, tenant_id: UUID, total: int) -> None:
    database = (url or "").strip()
    if not database:
        return
    from factory_os.domain.postgres import connect

    try:
        conn = connect(database)
    except Exception as exc:
        if _missing_relation(exc):
            return
        raise
    try:
        conn.execute(
            """
            INSERT INTO model_usage (tenant_id, tokens, updated_at)
            VALUES (%s, %s, now())
            ON CONFLICT (tenant_id) DO UPDATE
            SET tokens = EXCLUDED.tokens,
                updated_at = now()
            """,
            (str(tenant_id), int(total)),
        )
        conn.commit()
    except Exception as exc:
        if _missing_relation(exc):
            return
        raise
    finally:
        conn.close()


def _missing_relation(exc: BaseException) -> bool:
    import psycopg

    return isinstance(exc, psycopg.errors.UndefinedTable)
