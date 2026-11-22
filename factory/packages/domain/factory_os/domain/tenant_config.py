"""Tenant industry and module flags. Data only; the operator console is phase 4."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

_MEMORY: dict[UUID, "TenantConfig"] = {}


@dataclass(frozen=True)
class TenantConfig:
    industry: str = "closet"
    modules: tuple[str, ...] = field(default_factory=tuple)


def clear_memory_tenant_configs() -> None:
    _MEMORY.clear()


def get_tenant_config(tenant_id: UUID, *, url: str | None = None) -> TenantConfig:
    if url:
        try:
            return _load_postgres(url, tenant_id)
        except Exception:
            # Unreachable or incomplete schema: fall back to memory rather
            # than failing every module-gated request (auth probes included).
            pass
    return _MEMORY.get(tenant_id, TenantConfig())


def put_tenant_config(
    tenant_id: UUID,
    *,
    industry: str,
    modules: list[str] | tuple[str, ...] | None = None,
    url: str | None = None,
    name: str = "Business",
) -> TenantConfig:
    clean_industry = (industry or "closet").strip().lower() or "closet"
    seen: set[str] = set()
    ordered: list[str] = []
    for raw in modules or []:
        item = str(raw).strip()
        if not item or item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    clean_modules = tuple(ordered)
    config = TenantConfig(industry=clean_industry, modules=clean_modules)
    if url:
        _store_postgres(url, tenant_id, config, name=name)
        return config
    _MEMORY[tenant_id] = config
    return config


def _load_postgres(url: str, tenant_id: UUID) -> TenantConfig:
    from factory_os.domain.postgres import tenant_connection

    with tenant_connection(url, tenant_id) as conn:
        row = conn.execute(
            "SELECT industry, enabled_modules FROM tenants WHERE id = %s",
            (str(tenant_id),),
        ).fetchone()
    if row is None:
        return TenantConfig()
    raw_modules = row["enabled_modules"]
    modules: tuple[str, ...] = ()
    if isinstance(raw_modules, list):
        modules = tuple(str(m) for m in raw_modules)
    elif isinstance(raw_modules, dict):
        modules = tuple(str(k) for k, v in raw_modules.items() if v)
    return TenantConfig(industry=str(row["industry"] or "closet"), modules=modules)


def _store_postgres(url: str, tenant_id: UUID, config: TenantConfig, *, name: str) -> None:
    from psycopg.types.json import Json

    from factory_os.domain.postgres import tenant_connection

    with tenant_connection(url, tenant_id) as conn:
        conn.execute(
            """
            INSERT INTO tenants (id, name, industry, enabled_modules)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE
              SET industry = EXCLUDED.industry,
                  enabled_modules = EXCLUDED.enabled_modules
            """,
            (str(tenant_id), name, config.industry, Json(list(config.modules))),
        )


def as_dict(config: TenantConfig) -> dict[str, Any]:
    return {"industry": config.industry, "modules": list(config.modules)}
