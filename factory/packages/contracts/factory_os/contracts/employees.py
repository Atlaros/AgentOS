from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from factory_os.contracts.skills import (
    ACCOUNTING_SKILLS,
    ADRI_SKILLS,
    ANALYST_SKILLS,
    BBE_ACCOUNTING,
    BBE_ANALYST,
    BBE_CATALOG,
    BBE_COBROS,
    BBE_INVENTORY,
    BBE_OPS,
    BBE_POSTVENTA,
    BBE_SALES,
    BBE_SUPPLIERS,
    CATALOG_SKILLS,
    COBROS_SKILLS,
    INVENTORY_SKILLS,
    OPS_SKILLS,
    POSTVENTA_SKILLS,
    SUPPLIER_SKILLS,
    Skill,
)
from factory_os.domain.models import EmployeeRole

# permission -> allowed tools. Skills never appear here.
# Modules an employee of this base_role may staff on the canvas (ADR-027).
CANVAS_MODULES_BY_ROLE: dict[EmployeeRole, frozenset[str]] = {
    EmployeeRole.SALES: frozenset({"whatsapp", "mostrador", "pedido", "catalogo"}),
    EmployeeRole.COBROS: frozenset({"cobros"}),
    EmployeeRole.OPS: frozenset({"pedido", "cobros"}),
    EmployeeRole.POSTVENTA: frozenset({"whatsapp", "pedido"}),
    EmployeeRole.INVENTORY: frozenset({"catalogo", "proveedores"}),
    EmployeeRole.CATALOG_ADMIN: frozenset({"catalogo"}),
    EmployeeRole.ACCOUNTING: frozenset({"caja", "contabilidad"}),
    EmployeeRole.ANALYST: frozenset({"analitica", "reportes"}),
    EmployeeRole.SUPPLIERS: frozenset({"proveedores", "catalogo"}),
}

ROLE_PERMISSIONS: dict[EmployeeRole, frozenset[str]] = {
    EmployeeRole.SALES: frozenset(
        {
            "catalog.search",
            "cart.add",
            "cart.remove",
            "order.create",
            "payment.status",
            "send_product_image",
        }
    ),
    EmployeeRole.COBROS: frozenset({"payment.create_qr", "payment.status", "notice.send"}),
    EmployeeRole.OPS: frozenset({"customer.update_profile", "delivery.create", "payment.status"}),
    EmployeeRole.POSTVENTA: frozenset({"catalog.search", "payment.status", "notice.send"}),
    EmployeeRole.INVENTORY: frozenset({"catalog.search", "inventory.adjust"}),
    EmployeeRole.CATALOG_ADMIN: frozenset({"catalog.search", "catalog.upsert", "catalog.disable"}),
    EmployeeRole.ACCOUNTING: frozenset({"cash.record", "cash.ledger", "ledger.read", "invoice.issue"}),
    EmployeeRole.ANALYST: frozenset({"metrics.summary"}),
    EmployeeRole.SUPPLIERS: frozenset({"catalog.search", "stock.receive", "supplier.alert"}),
}

SKILLS_BY_ROLE: dict[EmployeeRole, tuple[Skill, ...]] = {
    EmployeeRole.SALES: ADRI_SKILLS,
    EmployeeRole.COBROS: COBROS_SKILLS,
    EmployeeRole.OPS: OPS_SKILLS,
    EmployeeRole.POSTVENTA: POSTVENTA_SKILLS,
    EmployeeRole.INVENTORY: INVENTORY_SKILLS,
    EmployeeRole.CATALOG_ADMIN: CATALOG_SKILLS,
    EmployeeRole.ACCOUNTING: ACCOUNTING_SKILLS,
    EmployeeRole.ANALYST: ANALYST_SKILLS,
    EmployeeRole.SUPPLIERS: SUPPLIER_SKILLS,
}

BBE_BY_ROLE: dict[EmployeeRole, tuple[str, ...]] = {
    EmployeeRole.SALES: BBE_SALES,
    EmployeeRole.COBROS: BBE_COBROS,
    EmployeeRole.OPS: BBE_OPS,
    EmployeeRole.POSTVENTA: BBE_POSTVENTA,
    EmployeeRole.INVENTORY: BBE_INVENTORY,
    EmployeeRole.CATALOG_ADMIN: BBE_CATALOG,
    EmployeeRole.ACCOUNTING: BBE_ACCOUNTING,
    EmployeeRole.ANALYST: BBE_ANALYST,
    EmployeeRole.SUPPLIERS: BBE_SUPPLIERS,
}

_STAFF_ROLES = frozenset(
    {
        EmployeeRole.INVENTORY,
        EmployeeRole.CATALOG_ADMIN,
        EmployeeRole.ACCOUNTING,
        EmployeeRole.ANALYST,
        EmployeeRole.SUPPLIERS,
    }
)
CATALOG_WRITE_TOOLS = frozenset({"catalog.upsert", "catalog.disable"})
PAYMENT_TOOLS = frozenset({"payment.create_qr", "payment.status"})
PAYMENT_WRITE_TOOLS = frozenset({"payment.create_qr"})
SALES_WRITE_TOOLS = frozenset({"cart.add", "cart.remove", "order.create"})
DELIVERY_TOOLS = frozenset({"delivery.create"})
INVENTORY_WRITE_TOOLS = frozenset({"inventory.adjust", "stock.receive"})
CASH_WRITE_TOOLS = frozenset({"cash.record"})


@dataclass(frozen=True)
class ConceptualRole:
    key: str
    employee_name: str
    responsibility: str
    runtime: bool


CONCEPTUAL_ROLES: tuple[ConceptualRole, ...] = (
    ConceptualRole("orchestrator", "Coordinador", "WHO: routing y carpeta. No ejecuta negocio.", True),
    ConceptualRole("sales", "Adri", "Atención comercial + ventas. No cobra ni edita catálogo.", True),
    ConceptualRole("collections", "Cobros", "QR y estado de pago vía adaptador.", True),
    ConceptualRole("ops", "Operaciones", "Perfil y envío después de pago confirmado.", True),
    ConceptualRole("postventa", "Postventa", "Pedidos entregados, incidencias, handoff a Adri.", True),
    ConceptualRole("inventory", "Inventario", "Stock y ajuste interno. No WhatsApp de venta.", True),
    ConceptualRole("catalog_admin", "Catálogo", "Alta/baja/edición de ficha. Nunca WhatsApp cliente.", True),
    ConceptualRole("accounting", "Contabilidad", "Caja y flujo de dinero. No cobra con QR.", True),
    ConceptualRole("analyst", "Analista", "Métricas de negocio. Solo lectura.", True),
    ConceptualRole("suppliers", "Proveedores", "Ingreso de stock. Alerta de falta; contacto futuro.", True),
)


@dataclass(frozen=True)
class EmployeeContract:
    key: str
    name: str
    role: EmployeeRole | None
    customer_whatsapp: bool
    skills: tuple[Skill, ...]
    bbe: tuple[str, ...]
    permissions: frozenset[str]


EMPLOYEE_REGISTRY: tuple[EmployeeContract, ...] = (
    EmployeeContract("orchestrator", "Coordinador", None, True, (), (), frozenset()),
    EmployeeContract(
        "sales",
        "Adri",
        EmployeeRole.SALES,
        True,
        ADRI_SKILLS,
        BBE_SALES,
        ROLE_PERMISSIONS[EmployeeRole.SALES],
    ),
    EmployeeContract(
        "collections",
        "Cobros",
        EmployeeRole.COBROS,
        True,
        COBROS_SKILLS,
        BBE_COBROS,
        ROLE_PERMISSIONS[EmployeeRole.COBROS],
    ),
    EmployeeContract(
        "ops",
        "Operaciones",
        EmployeeRole.OPS,
        True,
        OPS_SKILLS,
        BBE_OPS,
        ROLE_PERMISSIONS[EmployeeRole.OPS],
    ),
    EmployeeContract(
        "postventa",
        "Postventa",
        EmployeeRole.POSTVENTA,
        True,
        POSTVENTA_SKILLS,
        BBE_POSTVENTA,
        ROLE_PERMISSIONS[EmployeeRole.POSTVENTA],
    ),
    EmployeeContract(
        "inventory",
        "Inventario",
        EmployeeRole.INVENTORY,
        False,
        INVENTORY_SKILLS,
        BBE_INVENTORY,
        ROLE_PERMISSIONS[EmployeeRole.INVENTORY],
    ),
    EmployeeContract(
        "catalog_admin",
        "Catálogo",
        EmployeeRole.CATALOG_ADMIN,
        False,
        CATALOG_SKILLS,
        BBE_CATALOG,
        ROLE_PERMISSIONS[EmployeeRole.CATALOG_ADMIN],
    ),
    EmployeeContract(
        "accounting",
        "Contabilidad",
        EmployeeRole.ACCOUNTING,
        False,
        ACCOUNTING_SKILLS,
        BBE_ACCOUNTING,
        ROLE_PERMISSIONS[EmployeeRole.ACCOUNTING],
    ),
    EmployeeContract(
        "analyst",
        "Analista",
        EmployeeRole.ANALYST,
        False,
        ANALYST_SKILLS,
        BBE_ANALYST,
        ROLE_PERMISSIONS[EmployeeRole.ANALYST],
    ),
    EmployeeContract(
        "suppliers",
        "Proveedores",
        EmployeeRole.SUPPLIERS,
        False,
        SUPPLIER_SKILLS,
        BBE_SUPPLIERS,
        ROLE_PERMISSIONS[EmployeeRole.SUPPLIERS],
    ),
)


@dataclass(frozen=True)
class Identity:
    employee_name: str
    role: EmployeeRole
    tenant_id: UUID

    @property
    def permissions(self) -> frozenset[str]:
        return ROLE_PERMISSIONS[self.role]

    @property
    def skills(self) -> tuple[Skill, ...]:
        return SKILLS_BY_ROLE[self.role]

    @property
    def bbe(self) -> tuple[str, ...]:
        return BBE_BY_ROLE[self.role]


def identity_for(role: EmployeeRole, tenant_id: UUID) -> Identity:
    names = {
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
    name = names[role]
    try:
        from factory_os.domain.tenant_employees import display_name_for

        name = display_name_for(tenant_id, role)
    except ImportError:
        pass
    return Identity(employee_name=name, role=role, tenant_id=tenant_id)


def is_staff_role(role: EmployeeRole) -> bool:
    return role in _STAFF_ROLES


def contract_for(role: EmployeeRole) -> EmployeeContract:
    for item in EMPLOYEE_REGISTRY:
        if item.role is role:
            return item
    raise KeyError(role)
