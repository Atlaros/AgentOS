"""Read-only flow map and guarded catalog rules (ADR-023).

Node kinds, ports, and locked edges come from
``factory_os.contracts.nodes`` — this module does not redefine them.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal
from uuid import UUID, uuid4

from factory_os.contracts.employees import CANVAS_MODULES_BY_ROLE
from factory_os.contracts.nodes import (
    CORE_KINDS,
    LOCKED_EDGES,
    NODE_BY_KIND,
    OPTIONAL_EDGES,
    Port,
    node_ports,
    palette_kinds,
)
from factory_os.domain.models import EmployeeRole

RuleStatus = Literal["draft", "published"]
NodeFamily = Literal["module", "employee"]


@dataclass(frozen=True)
class FlowNode:
    id: str
    kind: str
    locked: bool = False
    family: NodeFamily = "module"
    employee_key: str | None = None
    display_name: str | None = None
    base_role: str | None = None


@dataclass(frozen=True)
class FlowEdge:
    source: str
    target: str
    port: Port
    locked: bool = False


@dataclass(frozen=True)
class FlowMap:
    nodes: tuple[FlowNode, ...]
    edges: tuple[FlowEdge, ...]


@dataclass(frozen=True)
class TeamAssignment:
    employee_key: str
    module: str


@dataclass
class CatalogRule:
    id: UUID
    when_event: str
    if_threshold: str
    then_action: str
    status: RuleStatus = "draft"
    tenant_id: UUID | None = None
    version: int = 1


_RULES: dict[UUID, CatalogRule] = {}
_VERSIONS: dict[UUID, list[CatalogRule]] = {}
# Published canvas kinds per tenant (memory). Postgres when url is set.
_PUBLISHED_MAPS: dict[UUID, tuple[str, ...]] = {}
_PUBLISHED_TEAMS: dict[UUID, tuple[TeamAssignment, ...]] = {}

_EMP_PREFIX = "emp:"


def clear_rules() -> None:
    _RULES.clear()
    _VERSIONS.clear()


def clear_published_flow_maps() -> None:
    _PUBLISHED_MAPS.clear()
    _PUBLISHED_TEAMS.clear()


def employee_node_id(employee_key: str) -> str:
    key = (employee_key or "").strip()
    if not key:
        raise ValueError("employee_key_required")
    if key.startswith(_EMP_PREFIX):
        return key
    return f"{_EMP_PREFIX}{key}"


def parse_employee_key(node_id: str) -> str | None:
    raw = (node_id or "").strip()
    if not raw.startswith(_EMP_PREFIX):
        return None
    key = raw[len(_EMP_PREFIX) :].strip()
    return key or None


def _is_employee_token(token: str) -> bool:
    return token.startswith(_EMP_PREFIX) or token == "employee"


def _normalize_flow_kinds(kinds: list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for raw in kinds or ():
        kind = str(raw).strip()
        if not kind or kind in seen:
            continue
        if _is_employee_token(kind) or parse_employee_key(kind):
            continue
        if kind not in NODE_BY_KIND:
            raise ValueError("unknown_kind")
        seen.add(kind)
        ordered.append(kind)
    if "pedido" not in seen or "cobros" not in seen:
        raise ValueError("path_locked")
    return tuple(ordered)


def try_flow_map(kinds: list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    """Validate canvas kinds without persisting (Try before publish)."""
    return _normalize_flow_kinds(kinds)


def propose_flow_kinds(
    current_kinds: list[str] | tuple[str, ...] | None = None,
    *,
    palette: list[str] | tuple[str, ...] | None = None,
) -> tuple[str, ...]:
    """Suggest kinds to place. Never publishes; caller must confirm."""
    seen: set[str] = set()
    ordered: list[str] = []
    for raw in current_kinds or ():
        kind = str(raw).strip()
        if not kind or kind in seen:
            continue
        if kind not in NODE_BY_KIND:
            continue
        seen.add(kind)
        ordered.append(kind)
    for required in ("pedido", "cobros"):
        if required not in seen and required in NODE_BY_KIND:
            seen.add(required)
            ordered.append(required)
    for raw in palette or ():
        kind = str(raw).strip()
        if not kind or kind in seen:
            continue
        if kind not in NODE_BY_KIND:
            continue
        seen.add(kind)
        ordered.append(kind)
    return tuple(ordered)


def publish_flow_map(
    tenant_id: UUID,
    kinds: list[str] | tuple[str, ...] | None,
    *,
    team: list[dict[str, str]] | tuple[dict[str, str], ...] | None = None,
    url: str | None = None,
) -> tuple[str, ...]:
    """Freeze canvas modules (and optional team assignments) for this business."""
    clean = _normalize_flow_kinds(kinds)
    assignments = _normalize_team(tenant_id, team, url=url)
    database = (url or "").strip()
    if database:
        _store_published_flow_map(database, tenant_id, clean, assignments)
        return clean
    _PUBLISHED_MAPS[tenant_id] = clean
    _PUBLISHED_TEAMS[tenant_id] = assignments
    return clean


def get_published_flow_kinds(
    tenant_id: UUID,
    *,
    url: str | None = None,
) -> tuple[str, ...] | None:
    """Return published canvas kinds, or None when the business has not published."""
    database = (url or "").strip()
    if database:
        try:
            loaded = _load_published_flow_map(database, tenant_id)
            if loaded is not None:
                return loaded
        except Exception:
            pass
    return _PUBLISHED_MAPS.get(tenant_id)


def get_published_team(
    tenant_id: UUID,
    *,
    url: str | None = None,
) -> tuple[TeamAssignment, ...]:
    """Return published employee→module assignments (empty if none)."""
    database = (url or "").strip()
    if database:
        try:
            loaded = _load_published_team(database, tenant_id)
            if loaded is not None:
                return loaded
        except Exception:
            pass
    return _PUBLISHED_TEAMS.get(tenant_id, ())


def _normalize_team(
    tenant_id: UUID,
    team: list[dict[str, str]] | tuple[dict[str, str], ...] | None,
    *,
    url: str | None = None,
) -> tuple[TeamAssignment, ...]:
    if not team:
        return ()
    from factory_os.domain.tenant_employees import list_employees

    roster = {
        row.employee_key: row
        for row in list_employees(tenant_id, include_archived=False, url=url)
    }
    seen: set[tuple[str, str]] = set()
    out: list[TeamAssignment] = []
    for raw in team:
        key = str(raw.get("employee_key") or "").strip()
        module = str(raw.get("module") or "").strip()
        if not key or not module:
            raise ValueError("team_incomplete")
        if key not in roster:
            raise ValueError("employee_not_in_roster")
        row = roster[key]
        if not row.enabled or row.archived:
            raise ValueError("employee_disabled")
        if module not in NODE_BY_KIND:
            raise ValueError("unknown_kind")
        allowed = CANVAS_MODULES_BY_ROLE.get(row.base_role, frozenset())
        if module not in allowed:
            raise ValueError("role_module_forbidden")
        pair = (key, module)
        if pair in seen:
            continue
        seen.add(pair)
        out.append(TeamAssignment(employee_key=key, module=module))
    return tuple(out)


def _store_published_flow_map(
    url: str,
    tenant_id: UUID,
    kinds: tuple[str, ...],
    team: tuple[TeamAssignment, ...] = (),
) -> None:
    from psycopg.types.json import Json

    from factory_os.domain.postgres import tenant_connection

    team_payload = [{"employee_key": row.employee_key, "module": row.module} for row in team]
    with tenant_connection(url, tenant_id) as conn:
        conn.execute(
            """
            INSERT INTO published_flow_maps (tenant_id, kinds, team)
            VALUES (%s, %s, %s)
            ON CONFLICT (tenant_id) DO UPDATE
              SET kinds = EXCLUDED.kinds,
                  team = EXCLUDED.team,
                  published_at = now()
            """,
            (str(tenant_id), Json(list(kinds)), Json(team_payload)),
        )


def _load_published_flow_map(url: str, tenant_id: UUID) -> tuple[str, ...] | None:
    from factory_os.domain.postgres import tenant_connection

    with tenant_connection(url, tenant_id) as conn:
        row = conn.execute(
            "SELECT kinds FROM published_flow_maps WHERE tenant_id = %s",
            (str(tenant_id),),
        ).fetchone()
    if row is None:
        return None
    raw = row["kinds"]
    if isinstance(raw, list):
        return tuple(str(item) for item in raw)
    return None


def _load_published_team(url: str, tenant_id: UUID) -> tuple[TeamAssignment, ...] | None:
    from factory_os.domain.postgres import tenant_connection

    with tenant_connection(url, tenant_id) as conn:
        row = conn.execute(
            "SELECT team FROM published_flow_maps WHERE tenant_id = %s",
            (str(tenant_id),),
        ).fetchone()
    if row is None:
        return None
    raw = row.get("team") if hasattr(row, "get") else row["team"]
    if raw is None:
        return ()
    if not isinstance(raw, list):
        return ()
    out: list[TeamAssignment] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        key = str(item.get("employee_key") or "").strip()
        module = str(item.get("module") or "").strip()
        if key and module:
            out.append(TeamAssignment(employee_key=key, module=module))
    return tuple(out)



def build_flow_map(enabled_modules: list[str] | tuple[str, ...]) -> FlowMap:
    enabled = {str(m).strip() for m in enabled_modules if str(m).strip()}
    kinds = sorted(CORE_KINDS | (enabled & set(NODE_BY_KIND)))
    nodes = tuple(
        FlowNode(id=kind, kind=kind, locked=kind in {"pedido", "cobros"}) for kind in kinds
    )
    edges: list[FlowEdge] = []
    present = {node.id for node in nodes}
    for source, target, port in LOCKED_EDGES:
        if source in present and target in present:
            edges.append(FlowEdge(source=source, target=target, port=port, locked=True))
    for source, target, port in OPTIONAL_EDGES:
        if source in present and target in present:
            edges.append(FlowEdge(source=source, target=target, port=port, locked=False))
    return FlowMap(nodes=nodes, edges=tuple(edges))


def connect_modules(
    source: str,
    target: str,
    port: str,
    *,
    enabled: list[str] | tuple[str, ...] = (),
) -> FlowEdge:
    """Join two modules on one port. A different port does not connect. The core path stays locked."""
    del enabled  # the palette is fixed; the caller passes modules for the same signature as the map
    origin = (source or "").strip()
    dest = (target or "").strip()
    port_name = (port or "").strip()
    if parse_employee_key(origin) or origin == "employee":
        raise ValueError("use_connect_employee")
    outs = node_ports(origin).get("out", ())
    ins = node_ports(dest).get("in", ())
    if port_name not in outs or port_name not in ins:
        raise ValueError("port_mismatch")
    triple = (origin, dest, port_name)
    if triple in LOCKED_EDGES:
        return FlowEdge(source=origin, target=dest, port=port_name, locked=True)  # type: ignore[arg-type]
    if port_name == "equipo":
        return FlowEdge(source=origin, target=dest, port=port_name, locked=False)  # type: ignore[arg-type]
    if origin in {"pedido", "cobros"} or dest in {"pedido", "cobros"}:
        if triple not in OPTIONAL_EDGES:
            raise ValueError("path_locked")
    return FlowEdge(source=origin, target=dest, port=port_name, locked=False)  # type: ignore[arg-type]


def place_employee(
    employee_key: str,
    *,
    display_name: str,
    base_role: EmployeeRole | str,
    present: list[str] | tuple[str, ...] = (),
    x: int = 24,
    y: int = 24,
) -> tuple[FlowNode, dict[str, int]]:
    """Place a roster employee on the canvas. Does not grant tools."""
    key = (employee_key or "").strip()
    if not key:
        raise ValueError("employee_key_required")
    node_id = employee_node_id(key)
    if node_id in {str(item).strip() for item in present if str(item).strip()}:
        raise ValueError("already_placed")
    role = base_role if isinstance(base_role, EmployeeRole) else EmployeeRole(str(base_role))
    name = (display_name or "").strip() or key
    return (
        FlowNode(
            id=node_id,
            kind="employee",
            locked=False,
            family="employee",
            employee_key=key,
            display_name=name,
            base_role=role.value,
        ),
        {"x": max(8, int(x)), "y": max(8, int(y))},
    )


def connect_employee_to_module(
    employee_node: str,
    module: str,
    *,
    base_role: EmployeeRole | str,
    port: str = "equipo",
) -> FlowEdge:
    """Assign an employee node to a business module on the equipo port."""
    origin = (employee_node or "").strip()
    dest = (module or "").strip()
    port_name = (port or "").strip()
    key = parse_employee_key(origin)
    if key is None:
        raise ValueError("employee_node_required")
    if dest not in NODE_BY_KIND:
        raise ValueError("unknown_kind")
    if port_name != "equipo":
        raise ValueError("port_mismatch")
    if "equipo" not in node_ports(dest).get("in", ()):
        raise ValueError("port_mismatch")
    role = base_role if isinstance(base_role, EmployeeRole) else EmployeeRole(str(base_role))
    allowed = CANVAS_MODULES_BY_ROLE.get(role, frozenset())
    if dest not in allowed:
        raise ValueError("role_module_forbidden")
    return FlowEdge(source=employee_node_id(key), target=dest, port="equipo", locked=False)


def compatible_targets(source: str, port: str) -> tuple[str, ...]:
    """Modules that accept this output port without breaking the locked path."""
    origin = (source or "").strip()
    port_name = (port or "").strip()
    if port_name not in node_ports(origin).get("out", ()):
        return ()
    targets: list[str] = []
    for dest in NODE_BY_KIND:
        if dest == origin:
            continue
        if port_name not in node_ports(dest).get("in", ()):
            continue
        try:
            connect_modules(origin, dest, port_name)
        except ValueError:
            continue
        targets.append(dest)
    return tuple(targets)


def compatible_by_source() -> dict[str, dict[str, list[str]]]:
    """Per-source map of ports to valid drop targets for the canvas highlight."""
    by_source: dict[str, dict[str, list[str]]] = {}
    for origin, contract in NODE_BY_KIND.items():
        by_port: dict[str, list[str]] = {}
        for port_name in contract.ports_out:
            by_port[port_name] = list(compatible_targets(origin, port_name))
        by_source[origin] = by_port
    return by_source


_LAYOUT_COLUMNS: tuple[tuple[str, ...], ...] = (
    ("whatsapp", "mostrador", "pedido", "cobros"),
    ("caja", "contabilidad", "proveedores", "catalogo"),
    ("analitica", "reportes", "conocimiento", "aprobacion"),
)


def layout_positions(node_ids: list[str] | tuple[str, ...]) -> dict[str, dict[str, int]]:
    """Default 2D placement for the guarded canvas. The locked path stays on the left."""
    present = {str(item).strip() for item in node_ids if str(item).strip()}
    placed: dict[str, dict[str, int]] = {}
    for column, column_ids in enumerate(_LAYOUT_COLUMNS):
        row = 0
        for node_id in column_ids:
            if node_id not in present:
                continue
            placed[node_id] = {"x": 24 + column * 220, "y": 24 + row * 96}
            row += 1
    extras = sorted(present - set(placed))
    for index, node_id in enumerate(extras):
        placed[node_id] = {"x": 24 + 2 * 220, "y": 24 + index * 96}
    return placed


def palette_modules() -> tuple[str, ...]:
    """Catalog pieces the operator may place. Nothing outside this set enters the canvas."""
    return palette_kinds()


def place_module(
    kind: str,
    *,
    present: list[str] | tuple[str, ...] = (),
    x: int = 24,
    y: int = 24,
) -> tuple[FlowNode, dict[str, int]]:
    """Add a catalog module to the canvas. Unknown kinds are rejected."""
    node_id = (kind or "").strip()
    if node_id not in NODE_BY_KIND:
        raise ValueError("unknown_module")
    if node_id in {str(item).strip() for item in present if str(item).strip()}:
        raise ValueError("already_placed")
    locked = node_id in {"pedido", "cobros"}
    return FlowNode(id=node_id, kind=node_id, locked=locked), {
        "x": max(8, int(x)),
        "y": max(8, int(y)),
    }


def attach_team_to_flow(
    flow: FlowMap,
    team: tuple[TeamAssignment, ...] | list[TeamAssignment],
    *,
    roster: list[dict[str, Any]] | tuple[dict[str, Any], ...] = (),
) -> FlowMap:
    """Overlay employee nodes and equipo edges from published team assignments."""
    by_key = {
        str(row.get("employee_key") or "").strip(): row
        for row in roster
        if str(row.get("employee_key") or "").strip()
    }
    nodes = list(flow.nodes)
    edges = list(flow.edges)
    present = {node.id for node in nodes}
    for assignment in team:
        key = assignment.employee_key
        module = assignment.module
        if module not in present:
            continue
        node_id = employee_node_id(key)
        if node_id not in present:
            meta = by_key.get(key, {})
            nodes.append(
                FlowNode(
                    id=node_id,
                    kind="employee",
                    locked=False,
                    family="employee",
                    employee_key=key,
                    display_name=str(meta.get("display_name") or key),
                    base_role=str(meta.get("base_role") or ""),
                )
            )
            present.add(node_id)
        edge = FlowEdge(source=node_id, target=module, port="equipo", locked=False)
        if not any(
            item.source == edge.source and item.target == edge.target and item.port == edge.port
            for item in edges
        ):
            edges.append(edge)
    return FlowMap(nodes=tuple(nodes), edges=tuple(edges))


def flow_map_as_dict(
    flow: FlowMap,
    *,
    published_kinds: tuple[str, ...] | list[str] | None = None,
    employee_palette: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
    published_team: tuple[TeamAssignment, ...] | list[TeamAssignment] | None = None,
) -> dict[str, Any]:
    node_ids = tuple(node.id for node in flow.nodes)
    payload: dict[str, Any] = {
        "nodes": [asdict(node) for node in flow.nodes],
        "edges": [asdict(edge) for edge in flow.edges],
        "compatible": compatible_by_source(),
        "positions": layout_positions(node_ids),
        "palette": list(palette_modules()),
        "employee_palette": list(employee_palette or ()),
        "published": published_kinds is not None,
        "published_kinds": list(published_kinds) if published_kinds is not None else None,
        "published_team": [
            {"employee_key": row.employee_key, "module": row.module}
            for row in (published_team or ())
        ],
    }
    return payload



def create_rule(
    *,
    when_event: str,
    if_threshold: str,
    then_action: str,
    tenant_id: UUID | None = None,
    url: str | None = None,
) -> CatalogRule:
    when = (when_event or "").strip()
    predicate = (if_threshold or "").strip()
    action = (then_action or "").strip()
    if not when or not predicate or not action:
        raise ValueError("rule_incomplete")
    if "pago confirmado" in action.lower() or "confirm_payment" in action.lower():
        raise ValueError("payment_confirm_forbidden")
    rule = CatalogRule(
        id=uuid4(),
        when_event=when,
        if_threshold=predicate,
        then_action=action,
        tenant_id=tenant_id,
    )
    database = (url or "").strip()
    if database:
        if tenant_id is None:
            raise ValueError("rule_tenant_required")
        _insert_rule(database, rule)
        return rule
    _RULES[rule.id] = rule
    return rule


def publish_rule(rule_id: UUID, *, url: str | None = None) -> CatalogRule:
    database = (url or "").strip()
    if database:
        return _publish_postgres(database, rule_id)
    rule = _RULES.get(rule_id)
    if rule is None:
        raise KeyError("rule_not_found")
    history = _VERSIONS.setdefault(rule_id, [])
    rule.status = "published"
    rule.version = len(history) + 1
    history.append(_copy_rule(rule))
    return rule


def revert_rule(rule_id: UUID, *, version: int, url: str | None = None) -> CatalogRule:
    database = (url or "").strip()
    if database:
        return _revert_postgres(database, rule_id, version)
    history = _VERSIONS.get(rule_id) or []
    snapshot = next((item for item in history if item.version == version), None)
    if snapshot is None:
        raise KeyError("rule_version_not_found")
    action = snapshot.then_action.lower()
    if "pago confirmado" in action or "confirm_payment" in action:
        raise ValueError("payment_confirm_forbidden")
    restored = _copy_rule(snapshot)
    _RULES[rule_id] = restored
    return restored


def update_rule(rule_id: UUID, *, then_action: str, url: str | None = None) -> CatalogRule:
    action = (then_action or "").strip()
    if not action:
        raise ValueError("rule_incomplete")
    if "pago confirmado" in action.lower() or "confirm_payment" in action.lower():
        raise ValueError("payment_confirm_forbidden")
    database = (url or "").strip()
    if database:
        return _update_postgres(database, rule_id, action)
    rule = _RULES.get(rule_id)
    if rule is None:
        raise KeyError("rule_not_found")
    rule.then_action = action
    return rule


def _copy_rule(rule: CatalogRule) -> CatalogRule:
    return CatalogRule(
        id=rule.id,
        when_event=rule.when_event,
        if_threshold=rule.if_threshold,
        then_action=rule.then_action,
        status=rule.status,
        tenant_id=rule.tenant_id,
        version=rule.version,
    )


def list_rules(*, url: str | None = None) -> list[CatalogRule]:
    database = (url or "").strip()
    if database:
        return _list_postgres(database)
    return list(_RULES.values())


def _insert_rule(url: str, rule: CatalogRule) -> None:
    from factory_os.domain.postgres import connect

    conn = connect(url)
    try:
        conn.execute(
            """
            INSERT INTO catalog_rules (id, tenant_id, when_event, if_threshold, then_action, status)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                str(rule.id),
                str(rule.tenant_id),
                rule.when_event,
                rule.if_threshold,
                rule.then_action,
                rule.status,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _publish_postgres(url: str, rule_id: UUID) -> CatalogRule:
    from factory_os.domain.postgres import connect

    conn = connect(url)
    try:
        current = conn.execute(
            """
            SELECT when_event, if_threshold, then_action
            FROM catalog_rules
            WHERE id = %s
            """,
            (str(rule_id),),
        ).fetchone()
        if current is None:
            raise KeyError("rule_not_found")
        next_version = conn.execute(
            """
            SELECT COALESCE(MAX(version), 0) + 1 AS version
            FROM catalog_rule_versions
            WHERE rule_id = %s
            """,
            (str(rule_id),),
        ).fetchone()["version"]
        conn.execute(
            """
            INSERT INTO catalog_rule_versions (rule_id, version, when_event, if_threshold, then_action)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                str(rule_id),
                next_version,
                current["when_event"],
                current["if_threshold"],
                current["then_action"],
            ),
        )
        row = conn.execute(
            """
            UPDATE catalog_rules
            SET status = 'published', version = %s
            WHERE id = %s
            RETURNING id, tenant_id, when_event, if_threshold, then_action, status, version
            """,
            (next_version, str(rule_id)),
        ).fetchone()
        conn.commit()
    finally:
        conn.close()
    if row is None:
        raise KeyError("rule_not_found")
    return _rule_from_row(row)


def _update_postgres(url: str, rule_id: UUID, then_action: str) -> CatalogRule:
    from factory_os.domain.postgres import connect

    conn = connect(url)
    try:
        row = conn.execute(
            """
            UPDATE catalog_rules
            SET then_action = %s
            WHERE id = %s
            RETURNING id, tenant_id, when_event, if_threshold, then_action, status, version
            """,
            (then_action, str(rule_id)),
        ).fetchone()
        conn.commit()
    finally:
        conn.close()
    if row is None:
        raise KeyError("rule_not_found")
    return _rule_from_row(row)


def _revert_postgres(url: str, rule_id: UUID, version: int) -> CatalogRule:
    from factory_os.domain.postgres import connect

    conn = connect(url)
    try:
        snapshot = conn.execute(
            """
            SELECT when_event, if_threshold, then_action
            FROM catalog_rule_versions
            WHERE rule_id = %s AND version = %s
            """,
            (str(rule_id), version),
        ).fetchone()
        if snapshot is None:
            raise KeyError("rule_version_not_found")
        action = str(snapshot["then_action"]).lower()
        if "pago confirmado" in action or "confirm_payment" in action:
            raise ValueError("payment_confirm_forbidden")
        row = conn.execute(
            """
            UPDATE catalog_rules
            SET when_event = %s,
                if_threshold = %s,
                then_action = %s,
                status = 'published',
                version = %s
            WHERE id = %s
            RETURNING id, tenant_id, when_event, if_threshold, then_action, status, version
            """,
            (
                snapshot["when_event"],
                snapshot["if_threshold"],
                snapshot["then_action"],
                version,
                str(rule_id),
            ),
        ).fetchone()
        conn.commit()
    finally:
        conn.close()
    if row is None:
        raise KeyError("rule_not_found")
    return _rule_from_row(row)


def _list_postgres(url: str) -> list[CatalogRule]:
    from factory_os.domain.postgres import connect

    conn = connect(url)
    try:
        rows = conn.execute(
            """
            SELECT id, tenant_id, when_event, if_threshold, then_action, status, version
            FROM catalog_rules
            ORDER BY created_at
            """
        ).fetchall()
    finally:
        conn.close()
    return [_rule_from_row(row) for row in rows]


def _rule_from_row(row: dict[str, Any]) -> CatalogRule:
    tenant = row["tenant_id"]
    return CatalogRule(
        id=row["id"] if isinstance(row["id"], UUID) else UUID(str(row["id"])),
        when_event=str(row["when_event"]),
        if_threshold=str(row["if_threshold"]),
        then_action=str(row["then_action"]),
        status=row["status"],
        tenant_id=tenant if isinstance(tenant, UUID) else UUID(str(tenant)),
        version=int(row["version"]) if row.get("version") is not None else 1,
    )


def rule_as_dict(rule: CatalogRule) -> dict[str, Any]:
    return {
        "id": str(rule.id),
        "when_event": rule.when_event,
        "if_threshold": rule.if_threshold,
        "then_action": rule.then_action,
        "status": rule.status,
        "version": rule.version,
        "tenant_id": str(rule.tenant_id) if rule.tenant_id else None,
    }
