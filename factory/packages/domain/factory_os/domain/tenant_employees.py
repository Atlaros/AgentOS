"""Per-tenant digital employee roster (ADR-026).

Catalog roles live in contracts. This module stores enablement, display name,
style, and clones. Clones inherit a base_role only — never new tools.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID, uuid4

from factory_os.contracts.employees import EMPLOYEE_REGISTRY
from factory_os.domain.models import EmployeeRole

LOCKED_BASE_ROLES: frozenset[EmployeeRole] = frozenset(
    {EmployeeRole.SALES, EmployeeRole.COBROS}
)

_ROSTER: dict[UUID, dict[str, TenantEmployee]] = {}
_STYLE_MAX = 120
_NAME_MAX = 40


@dataclass
class TenantEmployee:
    employee_key: str
    base_role: EmployeeRole
    display_name: str
    style: str = ""
    enabled: bool = True
    is_clone: bool = False
    archived: bool = False


def clear_tenant_employees() -> None:
    _ROSTER.clear()


def _catalog_runtime_rows() -> list[TenantEmployee]:
    rows: list[TenantEmployee] = []
    for item in EMPLOYEE_REGISTRY:
        if item.role is None:
            continue
        rows.append(
            TenantEmployee(
                employee_key=item.key,
                base_role=item.role,
                display_name=item.name,
                style="",
                enabled=True,
                is_clone=False,
                archived=False,
            )
        )
    return rows


def ensure_tenant_roster(tenant_id: UUID, *, url: str | None = None) -> list[TenantEmployee]:
    """Seed missing catalog rows. Idempotent. Does not revive archived clones."""
    if url:
        _ensure_postgres(tenant_id, url)
    else:
        bucket = _ROSTER.setdefault(tenant_id, {})
        for row in _catalog_runtime_rows():
            if row.employee_key not in bucket:
                bucket[row.employee_key] = TenantEmployee(
                    employee_key=row.employee_key,
                    base_role=row.base_role,
                    display_name=row.display_name,
                    style=row.style,
                    enabled=row.enabled,
                    is_clone=False,
                    archived=False,
                )
    return list_employees(tenant_id, include_archived=True, url=url, _seeded=True)


def list_employees(
    tenant_id: UUID,
    *,
    include_archived: bool = False,
    url: str | None = None,
    _seeded: bool = False,
) -> list[TenantEmployee]:
    if not _seeded:
        ensure_tenant_roster(tenant_id, url=url)
        return list_employees(
            tenant_id, include_archived=include_archived, url=url, _seeded=True
        )
    if url:
        return _list_postgres(tenant_id, url, include_archived=include_archived)
    rows = list(_ROSTER.get(tenant_id, {}).values())
    if not include_archived:
        rows = [row for row in rows if not row.archived]
    return sorted(rows, key=lambda row: (row.is_clone, row.employee_key))


def enabled_base_roles(tenant_id: UUID, *, url: str | None = None) -> frozenset[EmployeeRole]:
    """Roles the orchestrator may choose for WHO (catalog + clones collapsed to base)."""
    roles: set[EmployeeRole] = set()
    for row in list_employees(tenant_id, include_archived=False, url=url):
        if row.enabled:
            roles.add(row.base_role)
    return frozenset(roles)


def display_name_for(
    tenant_id: UUID,
    role: EmployeeRole,
    *,
    url: str | None = None,
) -> str:
    """Prefer the catalog (non-clone) display name for a base role."""
    for row in list_employees(tenant_id, include_archived=False, url=url):
        if row.base_role is role and not row.is_clone:
            return row.display_name
    for row in list_employees(tenant_id, include_archived=False, url=url):
        if row.base_role is role and row.enabled:
            return row.display_name
    defaults = {
        EmployeeRole.SALES: "Adri",
        EmployeeRole.COBROS: "Cobros",
        EmployeeRole.OPS: "Operaciones",
        EmployeeRole.POSTVENTA: "Postventa",
        EmployeeRole.INVENTORY: "Inventario",
        EmployeeRole.CATALOG_ADMIN: "Catálogo",
        EmployeeRole.ACCOUNTING: "Contabilidad",
        EmployeeRole.ANALYST: "Analista",
        EmployeeRole.SUPPLIERS: "Proveedores",
    }
    return defaults.get(role, role.value)


def set_employee_enabled(
    tenant_id: UUID,
    employee_key: str,
    enabled: bool,
    *,
    url: str | None = None,
) -> TenantEmployee:
    ensure_tenant_roster(tenant_id, url=url)
    row = _get(tenant_id, employee_key, url=url)
    if row.base_role in LOCKED_BASE_ROLES and not enabled and not row.is_clone:
        raise ValueError(f"employee_locked:{row.employee_key}")
    if row.archived and enabled:
        raise ValueError("employee_archived")
    row.enabled = bool(enabled)
    _save(tenant_id, row, url=url)
    return row


def set_employee_profile(
    tenant_id: UUID,
    employee_key: str,
    *,
    display_name: str | None = None,
    style: str | None = None,
    url: str | None = None,
) -> TenantEmployee:
    ensure_tenant_roster(tenant_id, url=url)
    row = _get(tenant_id, employee_key, url=url)
    if display_name is not None:
        name = display_name.strip()
        if not name:
            raise ValueError("display_name_required")
        row.display_name = name[:_NAME_MAX]
    if style is not None:
        row.style = style.strip()[:_STYLE_MAX]
    _save(tenant_id, row, url=url)
    return row


def clone_employee(
    tenant_id: UUID,
    *,
    base_role: EmployeeRole,
    display_name: str,
    style: str = "",
    url: str | None = None,
) -> TenantEmployee:
    ensure_tenant_roster(tenant_id, url=url)
    name = (display_name or "").strip()
    if not name:
        raise ValueError("display_name_required")
    if base_role not in {item.role for item in EMPLOYEE_REGISTRY if item.role is not None}:
        raise ValueError(f"unknown_base_role:{base_role}")
    slug = _slug(name)
    key = f"{base_role.value}__{slug}_{uuid4().hex[:6]}"
    row = TenantEmployee(
        employee_key=key,
        base_role=base_role,
        display_name=name[:_NAME_MAX],
        style=(style or "").strip()[:_STYLE_MAX],
        enabled=True,
        is_clone=True,
        archived=False,
    )
    _save(tenant_id, row, url=url)
    return row


def archive_employee(
    tenant_id: UUID,
    employee_key: str,
    *,
    url: str | None = None,
) -> TenantEmployee:
    ensure_tenant_roster(tenant_id, url=url)
    row = _get(tenant_id, employee_key, url=url)
    if not row.is_clone:
        raise ValueError("catalog_employee_not_archivable")
    row.archived = True
    row.enabled = False
    _save(tenant_id, row, url=url)
    return row


def employee_as_dict(row: TenantEmployee) -> dict[str, object]:
    return {
        "employee_key": row.employee_key,
        "base_role": row.base_role.value,
        "display_name": row.display_name,
        "style": row.style,
        "enabled": row.enabled,
        "is_clone": row.is_clone,
        "archived": row.archived,
        "locked": row.base_role in LOCKED_BASE_ROLES and not row.is_clone,
    }


def _slug(name: str) -> str:
    raw = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return (raw or "emp")[:24]


def _get(tenant_id: UUID, employee_key: str, *, url: str | None) -> TenantEmployee:
    if url:
        rows = _list_postgres(tenant_id, url, include_archived=True)
        for row in rows:
            if row.employee_key == employee_key:
                return row
        raise KeyError(f"employee_not_found:{employee_key}")
    bucket = _ROSTER.get(tenant_id) or {}
    row = bucket.get(employee_key)
    if row is None:
        raise KeyError(f"employee_not_found:{employee_key}")
    return row


def _save(tenant_id: UUID, row: TenantEmployee, *, url: str | None) -> None:
    if url:
        _upsert_postgres(tenant_id, row, url)
        return
    _ROSTER.setdefault(tenant_id, {})[row.employee_key] = row


def _ensure_postgres(tenant_id: UUID, url: str) -> None:
    from factory_os.domain.postgres import tenant_connection

    with tenant_connection(url, tenant_id) as conn:
        for row in _catalog_runtime_rows():
            conn.execute(
                """
                INSERT INTO tenant_employees (
                    tenant_id, employee_key, base_role, display_name, style,
                    enabled, is_clone, archived
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, employee_key) DO NOTHING
                """,
                (
                    str(tenant_id),
                    row.employee_key,
                    row.base_role.value,
                    row.display_name,
                    row.style,
                    row.enabled,
                    False,
                    False,
                ),
            )
        conn.commit()


def _list_postgres(
    tenant_id: UUID, url: str, *, include_archived: bool
) -> list[TenantEmployee]:
    from factory_os.domain.postgres import tenant_connection

    with tenant_connection(url, tenant_id) as conn:
        if include_archived:
            rows = conn.execute(
                """
                SELECT employee_key, base_role, display_name, style, enabled, is_clone, archived
                FROM tenant_employees
                WHERE tenant_id = %s
                ORDER BY is_clone, employee_key
                """,
                (str(tenant_id),),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT employee_key, base_role, display_name, style, enabled, is_clone, archived
                FROM tenant_employees
                WHERE tenant_id = %s AND NOT archived
                ORDER BY is_clone, employee_key
                """,
                (str(tenant_id),),
            ).fetchall()
    return [
        TenantEmployee(
            employee_key=str(row["employee_key"]),
            base_role=EmployeeRole(str(row["base_role"])),
            display_name=str(row["display_name"]),
            style=str(row["style"] or ""),
            enabled=bool(row["enabled"]),
            is_clone=bool(row["is_clone"]),
            archived=bool(row["archived"]),
        )
        for row in rows
    ]


def _upsert_postgres(tenant_id: UUID, row: TenantEmployee, url: str) -> None:
    from factory_os.domain.postgres import tenant_connection

    with tenant_connection(url, tenant_id) as conn:
        conn.execute(
            """
            INSERT INTO tenant_employees (
                tenant_id, employee_key, base_role, display_name, style,
                enabled, is_clone, archived
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, employee_key) DO UPDATE SET
                display_name = EXCLUDED.display_name,
                style = EXCLUDED.style,
                enabled = EXCLUDED.enabled,
                is_clone = EXCLUDED.is_clone,
                archived = EXCLUDED.archived
            """,
            (
                str(tenant_id),
                row.employee_key,
                row.base_role.value,
                row.display_name,
                row.style,
                row.enabled,
                row.is_clone,
                row.archived,
            ),
        )
        conn.commit()
