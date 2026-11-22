#!/usr/bin/env python3
"""Render lab boot: ensure sibling DB `agentos`, migrate, then start the API.

One Render Postgres free instance hosts `factory_agentos` (Blueprint default) and
`agentos` (created here). Tables never share a catalog.
"""

from __future__ import annotations

import os
import subprocess
import sys
from urllib.parse import urlparse, urlunparse

LAB_DB_NAME = "agentos"


def _require(name: str) -> str:
    value = (os.environ.get(name) or "").strip()
    if not value:
        raise SystemExit(f"missing_{name.lower()}")
    return value


def _to_asyncpg(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://") :]
    raise SystemExit("unsupported_database_url_scheme")


def _to_sqlalchemy(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return "postgresql://" + url[len("postgresql+asyncpg://") :]
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://") :]
    return url


def _swap_database(url: str, database: str) -> str:
    parsed = urlparse(url)
    return urlunparse(parsed._replace(path=f"/{database}"))


def _ensure_database(admin_url: str, database: str) -> None:
    from sqlalchemy import create_engine, text

    if not database.isidentifier() or database != LAB_DB_NAME:
        raise SystemExit("refusing_unexpected_database_name")

    # Prefer the Blueprint catalog as maintenance DB; fall back to `postgres`
    # when the provider exposes it. Never create tables in the Factory catalog.
    candidates = [
        _to_sqlalchemy(admin_url),
        _swap_database(_to_sqlalchemy(admin_url), "postgres"),
    ]
    last_error: Exception | None = None
    for maintenance in candidates:
        engine = create_engine(maintenance, isolation_level="AUTOCOMMIT")
        try:
            with engine.connect() as conn:
                exists = conn.execute(
                    text("SELECT 1 FROM pg_database WHERE datname = :name"),
                    {"name": database},
                ).fetchone()
                if exists is None:
                    conn.execute(text(f'CREATE DATABASE "{database}"'))
            return
        except Exception as exc:  # noqa: BLE001 — try next maintenance DB
            last_error = exc
        finally:
            engine.dispose()
    raise SystemExit(f"create_database_failed:{last_error}")


def main() -> int:
    explicit = (os.environ.get("AGENTOS_DATABASE_URL") or "").strip()
    shared = (os.environ.get("SHARED_POSTGRES_URL") or "").strip()

    if explicit:
        os.environ["AGENTOS_DATABASE_URL"] = _to_asyncpg(explicit)
    elif shared:
        _ensure_database(shared, LAB_DB_NAME)
        os.environ["AGENTOS_DATABASE_URL"] = _to_asyncpg(_swap_database(shared, LAB_DB_NAME))
    else:
        raise SystemExit("missing_agentos_database_url_or_shared_postgres_url")

    _require("AGENTOS_BOOTSTRAP_TOKEN")
    _require("AGENTOS_OAUTH_SIGNING_KEY")

    subprocess.check_call(["alembic", "upgrade", "head"], cwd="/app")
    os.execvp("agentos-api", ["agentos-api"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
