#!/usr/bin/env python3
"""Prepare a hosted Postgres (Supabase) for the API.

Applies pending migrations with the admin URL, then creates or aligns the
runtime role from DATABASE_RUNTIME_URL (LOGIN, NOSUPERUSER, NOBYPASSRLS) with
DML grants only, and checks that the role cannot bypass RLS. On Supabase it
also closes the Data API: `anon` and `authenticated` get no access to `public`.

Works with the direct connection or the Supabase pooler. Through the pooler the
user is `<role>.<project-ref>`; the role itself is `<role>`.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "packages" / "domain") not in sys.path:
    sys.path.insert(0, str(ROOT / "packages" / "domain"))

from factory_os.domain.postgres import (  # noqa: E402
    apply_migrations,
    assert_rls_runtime_role,
    ensure_local_rls_runtime_role,
)

DATA_API_ROLES = ("anon", "authenticated")


def close_data_api(admin_url: str) -> list[str]:
    """Revoke `public` from Supabase's Data API roles; returns the roles touched."""
    touched: list[str] = []
    with psycopg.connect(admin_url) as conn:
        for role in DATA_API_ROLES:
            exists = conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)).fetchone()
            if not exists:
                continue
            ident = sql.Identifier(role)
            for stmt in (
                "REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {}",
                "REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {}",
                "REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM {}",
                "ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM {}",
                "ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM {}",
                "ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON FUNCTIONS FROM {}",
            ):
                conn.execute(sql.SQL(stmt).format(ident))
            touched.append(role)
    return touched


def main() -> int:
    admin_url = os.environ.get("DATABASE_URL", "").strip()
    runtime_url = os.environ.get("DATABASE_RUNTIME_URL", "").strip()
    if not admin_url or not runtime_url:
        print("DATABASE_URL y DATABASE_RUNTIME_URL son obligatorias.", file=sys.stderr)
        return 2
    if admin_url == runtime_url:
        print("DATABASE_RUNTIME_URL debe usar un rol distinto al admin.", file=sys.stderr)
        return 2
    apply_migrations(admin_url)
    ensure_local_rls_runtime_role(admin_url, runtime_url)
    assert_rls_runtime_role(runtime_url)
    closed = close_data_api(admin_url)
    print("Migraciones aplicadas; rol runtime sin BYPASSRLS listo.")
    if closed:
        print(f"Data API cerrada en public para: {', '.join(closed)}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
