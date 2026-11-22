"""Canvas node catalog — single source for ports, module, autonomy, industries.

A canvas node is not a LangGraph node. The domain flow map and the panel
palette read this registry; they do not redefine it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Port = Literal["pedido", "pago_confirmado", "aviso", "aprobacion", "equipo"]
Industry = Literal["cafe", "ropa"]

_ALL_INDUSTRIES: tuple[Industry, ...] = ("cafe", "ropa")


@dataclass(frozen=True)
class NodeContract:
    kind: str
    ports_in: tuple[Port, ...]
    ports_out: tuple[Port, ...]
    module: str
    autonomy_action: str | None
    industries: tuple[Industry, ...]
    core: bool = False


NODE_CATALOG: tuple[NodeContract, ...] = (
    NodeContract(
        kind="whatsapp",
        ports_in=("equipo",),
        ports_out=("pedido", "aviso"),
        module="whatsapp",
        autonomy_action="reply_customer",
        industries=_ALL_INDUSTRIES,
        core=True,
    ),
    NodeContract(
        kind="mostrador",
        ports_in=("equipo",),
        ports_out=("pedido",),
        module="mostrador",
        autonomy_action=None,
        industries=_ALL_INDUSTRIES,
        core=True,
    ),
    NodeContract(
        kind="pedido",
        ports_in=("pedido", "equipo"),
        ports_out=("pedido",),
        module="pedido",
        autonomy_action=None,
        industries=_ALL_INDUSTRIES,
        core=True,
    ),
    NodeContract(
        kind="cobros",
        ports_in=("pedido", "equipo"),
        ports_out=("pago_confirmado", "aviso"),
        module="cobros",
        autonomy_action="confirm_payment",
        industries=_ALL_INDUSTRIES,
        core=True,
    ),
    NodeContract(
        kind="caja",
        ports_in=("pago_confirmado", "equipo"),
        ports_out=("aviso",),
        module="caja",
        autonomy_action=None,
        industries=_ALL_INDUSTRIES,
    ),
    NodeContract(
        kind="contabilidad",
        ports_in=("pago_confirmado", "equipo"),
        ports_out=(),
        module="contabilidad",
        autonomy_action="post_journal",
        industries=_ALL_INDUSTRIES,
    ),
    NodeContract(
        kind="proveedores",
        ports_in=("aviso", "equipo"),
        ports_out=("aviso",),
        module="proveedores",
        autonomy_action="adjust_stock",
        industries=_ALL_INDUSTRIES,
    ),
    NodeContract(
        kind="catalogo",
        ports_in=("equipo",),
        ports_out=("aviso",),
        module="catalogo",
        autonomy_action="adjust_stock",
        industries=_ALL_INDUSTRIES,
    ),
    NodeContract(
        kind="analitica",
        ports_in=("aviso", "equipo"),
        ports_out=(),
        module="analitica",
        autonomy_action=None,
        industries=_ALL_INDUSTRIES,
    ),
    NodeContract(
        kind="reportes",
        ports_in=("aviso", "equipo"),
        ports_out=("aviso",),
        module="reportes",
        autonomy_action=None,
        industries=_ALL_INDUSTRIES,
    ),
    NodeContract(
        kind="conocimiento",
        ports_in=("equipo",),
        ports_out=("aviso",),
        module="conocimiento",
        autonomy_action=None,
        industries=_ALL_INDUSTRIES,
    ),
    NodeContract(
        kind="aprobacion",
        ports_in=("aviso", "aprobacion", "equipo"),
        ports_out=("aprobacion",),
        module="aprobacion",
        autonomy_action=None,
        industries=_ALL_INDUSTRIES,
    ),
)

NODE_BY_KIND: dict[str, NodeContract] = {node.kind: node for node in NODE_CATALOG}

CORE_KINDS: frozenset[str] = frozenset(node.kind for node in NODE_CATALOG if node.core)

LOCKED_EDGES: tuple[tuple[str, str, Port], ...] = (
    ("whatsapp", "pedido", "pedido"),
    ("mostrador", "pedido", "pedido"),
    ("pedido", "cobros", "pedido"),
)

# Optional default edges when both ends are present on the map.
OPTIONAL_EDGES: tuple[tuple[str, str, Port], ...] = (
    ("cobros", "caja", "pago_confirmado"),
    ("caja", "contabilidad", "pago_confirmado"),
)


def node_ports(kind: str) -> dict[str, tuple[Port, ...]]:
    node = NODE_BY_KIND.get(kind)
    if node is None:
        return {}
    return {"in": node.ports_in, "out": node.ports_out}


def palette_kinds(*, industry: str | None = None) -> tuple[str, ...]:
    key = (industry or "").strip().lower()
    if key == "closet":
        key = "ropa"
    kinds: list[str] = []
    for node in NODE_CATALOG:
        if key and key not in node.industries:
            continue
        kinds.append(node.kind)
    return tuple(sorted(kinds))


def pago_confirmado_sources() -> tuple[str, ...]:
    return tuple(
        sorted(
            node.kind
            for node in NODE_CATALOG
            if "pago_confirmado" in node.ports_out
        )
    )
