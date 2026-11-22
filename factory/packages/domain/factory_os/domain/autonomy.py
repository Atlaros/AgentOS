"""Template autonomy floors.

Data for the operator. Tool authorization stays in the runtime.
A business can demand more care. It cannot loosen the platform floor.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

_RANK = {"never": 0, "recommend": 1, "approval": 2, "within_limits": 3}
_OVERRIDES: dict[UUID, dict[str, str]] = {}
_OVERRIDES_LOADED = False

# Same floor for cafe and ropa. Payment confirmation stays with the bank adapter.
_FLOOR: tuple[tuple[str, str], ...] = (
    ("confirm_payment", "never"),
    ("post_journal", "approval"),
    ("adjust_stock", "approval"),
    ("reply_customer", "within_limits"),
)


@dataclass(frozen=True)
class AutonomyGrant:
    action: str
    level: str


class AutonomyDenied(Exception):
    """The template floor refuses this tool. It does not grant a permission."""

    def __init__(self, action: str) -> None:
        super().__init__(action)
        self.action = action


_CONFIRM_TOOLS = frozenset({"payment.confirm"})
_TOOL_ACTION = {
    "inventory.adjust": "adjust_stock",
    "stock.receive": "adjust_stock",
    "journal.post": "post_journal",
    "notice.send": "reply_customer",
}


def template_autonomy(industry: str) -> tuple[AutonomyGrant, ...]:
    key = (industry or "").strip().lower()
    if key == "closet":
        key = "ropa"
    if key not in {"cafe", "ropa"}:
        raise KeyError(f"unknown_template:{industry}")
    return tuple(AutonomyGrant(action, level) for action, level in _FLOOR)


def tighten_autonomy(
    grants: tuple[AutonomyGrant, ...],
    *,
    action: str,
    level: str,
) -> tuple[AutonomyGrant, ...]:
    wanted = (level or "").strip()
    if wanted not in _RANK:
        raise ValueError(f"unknown_autonomy_level:{level}")
    target = (action or "").strip()
    current = next((item for item in grants if item.action == target), None)
    if current is None:
        raise ValueError(f"unknown_autonomy_action:{action}")
    if _RANK[wanted] > _RANK[current.level]:
        raise ValueError("autonomy_floor")
    return tuple(
        AutonomyGrant(item.action, wanted if item.action == target else item.level) for item in grants
    )


def clear_tenant_autonomy() -> None:
    global _OVERRIDES_LOADED
    _OVERRIDES.clear()
    _OVERRIDES_LOADED = False


def grants_for_tenant(
    tenant_id: UUID,
    *,
    industry: str,
    url: str | None = None,
) -> tuple[AutonomyGrant, ...]:
    """Template floor plus any tighter overrides for this business."""
    load_tenant_autonomy(url)
    grants = template_autonomy(industry)
    for action, level in _OVERRIDES.get(tenant_id, {}).items():
        grants = tighten_autonomy(grants, action=action, level=level)
    return grants


def set_tenant_autonomy(
    tenant_id: UUID,
    *,
    industry: str,
    action: str,
    level: str,
    url: str | None = None,
) -> tuple[AutonomyGrant, ...]:
    """Tighten one action for a business. Refuses to loosen the floor."""
    load_tenant_autonomy(url)
    grants = grants_for_tenant(tenant_id, industry=industry, url=url)
    tightened = tighten_autonomy(grants, action=action, level=level)
    wanted = (level or "").strip()
    target = (action or "").strip()
    bucket = _OVERRIDES.setdefault(tenant_id, {})
    bucket[target] = wanted
    _persist_override(url, tenant_id, target, wanted)
    return tightened


def load_tenant_autonomy(url: str | None) -> None:
    """Fill overrides from the database. A missing table leaves memory as it is."""
    global _OVERRIDES_LOADED
    database = (url or "").strip()
    if not database or _OVERRIDES_LOADED:
        return
    from factory_os.domain.postgres import connect

    try:
        conn = connect(database)
    except Exception as exc:
        if _missing_relation(exc):
            return
        raise
    try:
        rows = conn.execute(
            "SELECT tenant_id, action, level FROM tenant_autonomy"
        ).fetchall()
    except Exception as exc:
        if _missing_relation(exc):
            return
        raise
    finally:
        conn.close()
    for row in rows:
        tenant_id = row["tenant_id"] if isinstance(row["tenant_id"], UUID) else UUID(str(row["tenant_id"]))
        action = str(row.get("action") or "").strip()
        level = str(row.get("level") or "").strip()
        if action and level in _RANK:
            _OVERRIDES.setdefault(tenant_id, {})[action] = level
    _OVERRIDES_LOADED = True


def _persist_override(url: str | None, tenant_id: UUID, action: str, level: str) -> None:
    database = (url or "").strip()
    if not database:
        return
    from factory_os.domain.postgres import connect

    try:
        conn = connect(database)
    except Exception as exc:
        if _missing_relation(exc):
            return
        raise
    try:
        conn.execute(
            """
            INSERT INTO tenant_autonomy (tenant_id, action, level)
            VALUES (%s, %s, %s)
            ON CONFLICT (tenant_id, action) DO UPDATE
            SET level = EXCLUDED.level
            """,
            (str(tenant_id), action, level),
        )
        conn.commit()
    except Exception as exc:
        if _missing_relation(exc):
            return
        raise
    finally:
        conn.close()


def _missing_relation(exc: BaseException) -> bool:
    import psycopg

    return isinstance(exc, psycopg.errors.UndefinedTable)


def autonomy_decision(
    grants: tuple[AutonomyGrant, ...],
    tool_name: str,
    payload: dict[str, object] | None,
    *,
    confirmed: bool,
) -> tuple[str, str] | None:
    """Return ('deny', action) or ('confirm', action). None lets the tool run."""
    data = payload or {}
    if tool_name in _CONFIRM_TOOLS or data.get("mark_paid_from_text"):
        return ("deny", "confirm_payment")
    action = _TOOL_ACTION.get(tool_name)
    if action is None:
        return None
    grant = next((item for item in grants if item.action == action), None)
    if grant is None:
        return None
    if grant.level in {"never", "recommend"}:
        return ("deny", action)
    if grant.level == "approval" and not confirmed:
        return ("confirm", action)
    return None
