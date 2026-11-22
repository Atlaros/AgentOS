"""Tenant alert thresholds for Analítica.

Stock-low stays on each variant (`reorder_threshold` in Proveedores).
This record only holds the tenant-wide clocks the business can edit.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DEFAULT_QR_PENDING_HOURS = 24
DEFAULT_INACTIVE_DAYS = 30
MAX_QR_PENDING_HOURS = 24 * 30
MAX_INACTIVE_DAYS = 3650

STOCK_NOTE = "El stock bajo se configura por producto en Proveedores."


@dataclass(frozen=True)
class AnalyticsThresholds:
    qr_pending_hours: int = DEFAULT_QR_PENDING_HOURS
    inactive_days: int = DEFAULT_INACTIVE_DAYS
    digest_whatsapp_enabled: bool = False

    def to_public(self) -> dict[str, Any]:
        return {
            "qr_pending_hours": self.qr_pending_hours,
            "inactive_days": self.inactive_days,
            "digest_whatsapp_enabled": self.digest_whatsapp_enabled,
            "stock_note": STOCK_NOTE,
        }


def _positive_int(value: object, code: str, *, max_value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(code)
    if value < 1 or value > max_value:
        raise ValueError(code)
    return value


def merge_thresholds(current: AnalyticsThresholds, patch: dict[str, Any]) -> AnalyticsThresholds:
    """Apply a partial patch. Omitted keys keep the current tenant values."""
    hours = current.qr_pending_hours
    days = current.inactive_days
    digest = current.digest_whatsapp_enabled
    if "qr_pending_hours" in patch and patch["qr_pending_hours"] is not None:
        hours = _positive_int(
            patch["qr_pending_hours"],
            "bad_qr_pending_hours",
            max_value=MAX_QR_PENDING_HOURS,
        )
    if "inactive_days" in patch and patch["inactive_days"] is not None:
        days = _positive_int(
            patch["inactive_days"],
            "bad_inactive_days",
            max_value=MAX_INACTIVE_DAYS,
        )
    if "digest_whatsapp_enabled" in patch and patch["digest_whatsapp_enabled"] is not None:
        flag = patch["digest_whatsapp_enabled"]
        if not isinstance(flag, bool):
            raise ValueError("bad_digest_whatsapp_enabled")
        digest = flag
    return AnalyticsThresholds(
        qr_pending_hours=hours,
        inactive_days=days,
        digest_whatsapp_enabled=digest,
    )
