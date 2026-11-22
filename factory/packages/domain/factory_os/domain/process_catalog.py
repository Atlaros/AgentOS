"""Industry process catalog and operator-guided diagnosis (ADR-022)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

Status = Literal["covered", "partial", "gap"]

PROCESS_CATALOG: dict[str, tuple[dict[str, Any], ...]] = {
    "cafe": (
        {
            "id": "wa_order",
            "title": "Pedido por WhatsApp",
            "requires": ("whatsapp", "pedido", "cobros"),
        },
        {
            "id": "counter_sale",
            "title": "Venta en mostrador",
            "requires": ("mostrador", "caja", "pedido", "cobros"),
        },
        {
            "id": "restock",
            "title": "Reposición",
            "requires": ("proveedores", "catalogo"),
        },
        {
            "id": "bar_queue",
            "title": "Cola de barra",
            "requires": ("barra",),
        },
    ),
    "ropa": (
        {
            "id": "wa_order",
            "title": "Pedido por WhatsApp",
            "requires": ("whatsapp", "pedido", "cobros"),
        },
        {
            "id": "counter_sale",
            "title": "Venta en mostrador",
            "requires": ("mostrador", "caja", "pedido", "cobros"),
        },
        {
            "id": "ship",
            "title": "Envío tras pago",
            "requires": ("pedido", "cobros"),
        },
        {
            "id": "restock",
            "title": "Reposición",
            "requires": ("proveedores", "catalogo"),
        },
    ),
}


@dataclass(frozen=True)
class ProcessDiagnosis:
    process_id: str
    title: str
    status: Status
    evidence: tuple[str, ...]
    gaps: tuple[str, ...]


def catalog_for(industry: str) -> tuple[dict[str, Any], ...]:
    key = (industry or "").strip().lower()
    if key == "closet":
        key = "ropa"
    if key not in PROCESS_CATALOG:
        raise KeyError(f"unknown_industry:{industry}")
    return PROCESS_CATALOG[key]


def diagnose_processes(industry: str, enabled_modules: list[str] | tuple[str, ...]) -> list[ProcessDiagnosis]:
    enabled = {str(m).strip() for m in enabled_modules if str(m).strip()}
    out: list[ProcessDiagnosis] = []
    for process in catalog_for(industry):
        requires = tuple(process["requires"])
        present = tuple(m for m in requires if m in enabled)
        missing = tuple(m for m in requires if m not in enabled)
        if not missing:
            status: Status = "covered"
        elif present:
            status = "partial"
        else:
            status = "gap"
        out.append(
            ProcessDiagnosis(
                process_id=str(process["id"]),
                title=str(process["title"]),
                status=status,
                evidence=present,
                gaps=missing,
            )
        )
    return out


def diagnosis_as_dict(row: ProcessDiagnosis) -> dict[str, Any]:
    payload = asdict(row)
    payload["evidence"] = list(row.evidence)
    payload["gaps"] = list(row.gaps)
    return payload
