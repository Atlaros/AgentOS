"""Create a business from a cafe or ropa template (Factory phase 2)."""

from __future__ import annotations

from uuid import UUID, uuid4

from factory_os.domain.tenant_config import TenantConfig, put_tenant_config

# Shared palette from ADR-017 §3.2. Same modules for cafe and ropa in phase 2.
_SHARED_MODULES = (
    "whatsapp",
    "mostrador",
    "catalogo",
    "pedido",
    "cobros",
    "caja",
    "proveedores",
    "contabilidad",
    "analitica",
    "reportes",
    "conocimiento",
)

TEMPLATE_MODULES: dict[str, tuple[str, ...]] = {
    "cafe": _SHARED_MODULES,
    "ropa": _SHARED_MODULES,
    "closet": _SHARED_MODULES,
}


def provision_business(
    *,
    name: str,
    industry: str,
    url: str | None = None,
    tenant_id: UUID | None = None,
) -> UUID:
    """Create a tenant from a template. Memory by default; Postgres when url is set."""
    key = (industry or "").strip().lower()
    if key not in TEMPLATE_MODULES:
        raise ValueError(f"unknown_industry:{industry}")
    tid = tenant_id or uuid4()
    display_name = (name or "Business").strip() or "Business"
    industry = "ropa" if key == "closet" else key
    config = put_tenant_config(
        tid,
        industry=industry,
        modules=TEMPLATE_MODULES[key],
        url=url,
        name=display_name,
    )
    from factory_os.domain.operator_registry import register_business

    register_business(tid, name=display_name, config=config)
    from factory_os.domain.tenant_employees import ensure_tenant_roster

    ensure_tenant_roster(tid, url=url)
    if url:
        _seed_catalog(url, tid, key)
    return tid


def _seed_catalog(url: str, tenant_id: UUID, industry: str) -> None:
    import json
    import tempfile
    from pathlib import Path

    from factory_os.domain.postgres import seed_catalog
    from factory_os.domain.seed import catalog_seed_path, extra_seed_paths

    seed_kind = "closet" if industry in {"ropa", "closet"} else industry

    def _seed_rewritten(source: Path) -> None:
        payload = json.loads(source.read_text(encoding="utf-8"))
        payload["tenant_id"] = str(tenant_id)
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", encoding="utf-8", delete=False
        ) as handle:
            json.dump(payload, handle)
            tmp_path = Path(handle.name)
        try:
            seed_catalog(url, tenant_id, tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)

    _seed_rewritten(catalog_seed_path(seed_kind))
    for extra in extra_seed_paths(seed_kind):
        _seed_rewritten(extra)


def describe_provision(tenant_id: UUID, *, url: str | None = None) -> TenantConfig:
    from factory_os.domain.tenant_config import get_tenant_config

    return get_tenant_config(tenant_id, url=url)
