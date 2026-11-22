#!/usr/bin/env python3
"""Render lab boot: provision RLS runtime role, then start Factory API.

Uses the Blueprint Postgres admin URL (database `factory_agentos`) and creates a
separate `factory_runtime` role so DATABASE_RUNTIME_URL never equals DATABASE_URL.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import quote, urlparse, urlunparse

ROOT = Path(__file__).resolve().parents[1]
DOMAIN = ROOT / "packages" / "domain"
if str(DOMAIN) not in sys.path:
    sys.path.insert(0, str(DOMAIN))

from factory_os.domain.postgres import (  # noqa: E402
    assert_rls_runtime_role,
    ensure_local_rls_runtime_role,
)

RUNTIME_USER = "factory_runtime"


def _require(name: str) -> str:
    value = (os.environ.get(name) or "").strip()
    if not value:
        raise SystemExit(f"missing_{name.lower()}")
    return value


def _normalize(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://") :]
    return url


def _runtime_url(admin_url: str, password: str) -> str:
    parsed = urlparse(_normalize(admin_url))
    host = parsed.hostname or ""
    port = parsed.port or 5432
    database = (parsed.path or "/").lstrip("/") or "factory_agentos"
    userinfo = f"{quote(RUNTIME_USER, safe='')}:{quote(password, safe='')}"
    netloc = f"{userinfo}@{host}:{port}"
    return urlunparse(("postgresql", netloc, f"/{database}", "", "", ""))


def main() -> int:
    admin_url = _normalize(_require("DATABASE_URL"))
    os.environ["DATABASE_URL"] = admin_url

    runtime_url = (os.environ.get("DATABASE_RUNTIME_URL") or "").strip()
    if not runtime_url:
        password = _require("DATABASE_RUNTIME_PASSWORD")
        runtime_url = _runtime_url(admin_url, password)
        os.environ["DATABASE_RUNTIME_URL"] = runtime_url

    if _normalize(runtime_url) == admin_url:
        raise SystemExit("database_runtime_url_must_differ_from_admin")

    ensure_local_rls_runtime_role(admin_url, runtime_url)
    assert_rls_runtime_role(runtime_url)

    os.execvp("factory-os-api", ["factory-os-api"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
