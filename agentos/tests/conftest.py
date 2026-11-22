from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
async def _reset_async_db_engine() -> None:
    """Avoid asyncpg 'Future attached to a different loop' across pytest-asyncio tests."""
    yield
    from agentos.db.session import dispose_engine

    await dispose_engine()
