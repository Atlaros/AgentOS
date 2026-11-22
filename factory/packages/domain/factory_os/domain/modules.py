"""Which business modules are on. Empty config = unrestricted (legacy pilot)."""

from __future__ import annotations

from uuid import UUID

from factory_os.domain.tenant_config import get_tenant_config

# Panel and API prefixes that a module owns.
MODULE_API_PREFIXES: tuple[tuple[str, str], ...] = (
    ("/api/cash", "caja"),
    ("/api/ledger", "contabilidad"),
    ("/api/journal", "contabilidad"),
    ("/api/suppliers", "proveedores"),
    ("/api/purchase-orders", "proveedores"),
    ("/api/stock/receive", "proveedores"),
    ("/api/metrics", "analitica"),
    ("/api/analytics", "analitica"),
    ("/api/reports", "reportes"),
    ("/api/reminders", "reportes"),
    ("/api/alerts", "analitica"),
    ("/api/knowledge", "conocimiento"),
)

MODULE_NAV: tuple[tuple[str, str], ...] = (
    ("/cash", "caja"),
    ("/ledger", "contabilidad"),
    ("/suppliers", "proveedores"),
    ("/metrics", "analitica"),
    ("/reports", "reportes"),
    ("/knowledge", "conocimiento"),
)


def enabled_modules(tenant_id: UUID, *, url: str | None = None) -> tuple[str, ...] | None:
    """Return the active modules, or None when the tenant has no restriction."""
    modules = get_tenant_config(tenant_id, url=url).modules
    if not modules:
        return None
    return modules


def module_is_enabled(
    tenant_id: UUID,
    module: str,
    *,
    url: str | None = None,
) -> bool:
    active = enabled_modules(tenant_id, url=url)
    if active is None:
        return True
    return module in active


def module_for_api_path(path: str) -> str | None:
    clean = (path or "").split("?", 1)[0]
    for prefix, module in MODULE_API_PREFIXES:
        if clean == prefix or clean.startswith(prefix + "/"):
            return module
    return None


def nav_hrefs_for_modules(modules: tuple[str, ...] | None) -> frozenset[str] | None:
    """None = show every nav item. Otherwise only these hrefs from MODULE_NAV plus core."""
    if modules is None:
        return None
    allowed = {href for href, name in MODULE_NAV if name in modules}
    return frozenset(allowed)
