"""Seed chart of accounts for gerencial double-entry (ADR-011)."""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

ACCOUNT_TYPES = frozenset({"asset", "liability", "equity", "equity_draw", "income", "expense"})

SEED_ACCOUNTS: list[dict[str, Any]] = [
    {"code": "1100", "name": "Caja", "account_type": "asset"},
    {"code": "1200", "name": "Banco", "account_type": "asset"},
    {"code": "1300", "name": "Inventario", "account_type": "asset"},
    {"code": "1400", "name": "Cuentas por cobrar", "account_type": "asset"},
    {"code": "2100", "name": "Cuentas por pagar", "account_type": "liability"},
    {"code": "4100", "name": "Ventas", "account_type": "income"},
    {"code": "5100", "name": "Gastos operativos", "account_type": "expense"},
    {"code": "5110", "name": "Costo de ventas", "account_type": "expense"},
    {"code": "5200", "name": "Retiros del dueño", "account_type": "equity_draw"},
]


class ChartSeedStore(Protocol):
    def ensure_chart_accounts(self, tenant_id: UUID) -> list[Any]: ...


def ensure_chart_seed(store: ChartSeedStore, tenant_id: UUID) -> list[Any]:
    """Idempotent seed of ADR-011 minimum chart for a tenant."""
    return store.ensure_chart_accounts(tenant_id)
