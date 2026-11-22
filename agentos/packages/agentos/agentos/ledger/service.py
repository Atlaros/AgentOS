from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from agentos.db.models import LedgerEntry


async def append_ledger(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    entry_type: str,
    ref_type: str,
    ref_id: uuid.UUID,
    payload: dict[str, Any],
    entry_id: uuid.UUID | None = None,
) -> LedgerEntry:
    # Never store secrets in payload — caller responsibility; we strip common keys.
    safe = {k: v for k, v in payload.items() if "secret" not in k.lower() and "key" != k.lower()}
    identity = {"id": entry_id} if entry_id is not None else {}
    entry = LedgerEntry(
        organization_id=organization_id,
        entry_type=entry_type,
        ref_type=ref_type,
        ref_id=ref_id,
        payload=safe,
        **identity,
    )
    session.add(entry)
    await session.flush()
    return entry
